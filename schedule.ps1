# =============================================================================
# privacy-guardian - schedule.ps1
# Windows Task Scheduler registration. Mirrors the job-scout pattern exactly.
#
# Run from WSL terminal (recommended):
#   bash scan.sh schedule install
#   bash scan.sh schedule install -Profiles "name1,name2"
#   bash scan.sh schedule status
#   bash scan.sh schedule remove
#
# day_of_week examples in notify.yaml:
#   day_of_week: "Sunday"
#   day_of_week: "Monday,Wednesday,Friday"
#   day_of_week: "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday"
# =============================================================================

param(
    [Parameter(Position=0)]
    [ValidateSet("install","remove","status")]
    [string]$Command = "status",

    [string]$WslDistro  = "Ubuntu-20.04",
    [string]$Profiles   = "",
    [string]$TaskPrefix = "privacy-guardian"
)

$ErrorActionPreference = "Stop"

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$NotifyYaml = Join-Path $ScriptDir "config\notify.yaml"

function Get-ScheduleConfig {
    if (-not (Test-Path $NotifyYaml)) {
        Write-Error "config\notify.yaml not found. Copy notify.yaml.example and fill it in."
        exit 1
    }
    $lines = Get-Content $NotifyYaml

    $hour    = 8
    $minute  = 0
    $dow     = "Sunday"
    $enabled = $true

    foreach ($line in $lines) {
        $line = $line.Trim()
        if ($line -match "^hour:\s*(.+)$")        { $hour    = [int]($Matches[1] -replace '#.*','').Trim() }
        if ($line -match "^minute:\s*(.+)$")      { $minute  = [int]($Matches[1] -replace '#.*','').Trim() }
        if ($line -match "^day_of_week:\s*(.+)$") { $dow     = ($Matches[1] -replace '#.*','').Trim().Trim('"').Trim("'") }
        if ($line -match "^enabled:\s*false")     { $enabled = $false }
    }

    $dowParts = $dow.Split(",")
    $dowArray = @()
    foreach ($d in $dowParts) {
        $d = $d.Trim()
        if ($d -ne "") {
            $dowArray += [System.DayOfWeek]$d
        }
    }

    return @{
        Hour     = $hour
        Minute   = $minute
        DowRaw   = $dow
        DowArray = $dowArray
        Enabled  = $enabled
    }
}

function Build-WslArgument {
    param([string]$ProfilesArg)

    $wslPath = (wsl.exe -d $WslDistro wslpath -u ($ScriptDir.Replace("\", "/"))).Trim()

    $scanArgs = "--scheduled"
    if ($ProfilesArg -ne "") {
        $scanArgs = "--scheduled --profiles " + $ProfilesArg
    }

    $bashCmd = "cd " + '"' + $wslPath + '"' + " && bash scan.sh " + $scanArgs + ' >> "' + $wslPath + '/logs/cron.log" 2>&1'

    return "-d " + $WslDistro + ' -- bash -lc "' + $bashCmd + '"'
}

function Install-Tasks {
    $sched = Get-ScheduleConfig

    if (-not $sched.Enabled) {
        Write-Host "[schedule.ps1] scheduler.enabled=false - no task registered." -ForegroundColor Yellow
        return
    }

    $atTime = [datetime]::Today.AddHours($sched.Hour).AddMinutes($sched.Minute)

    Write-Host "[schedule.ps1] Registering task(s)..." -ForegroundColor Cyan
    Write-Host ("  Day(s)   : " + $sched.DowRaw)
    Write-Host ("  Time     : " + $sched.Hour + ":" + ("{0:D2}" -f $sched.Minute))
    Write-Host ("  Distro   : " + $WslDistro)
    $profDisplay = if ($Profiles -ne "") { $Profiles } else { "all" }
    Write-Host ("  Profiles : " + $profDisplay)
    Write-Host ""

    $profileList = @("all")
    if ($Profiles -ne "") {
        $profileList = $Profiles.Split(",")
    }

    foreach ($profId in $profileList) {
        $profId     = $profId.Trim()
        $taskName   = $TaskPrefix + "-" + $profId
        $profileArg = ""
        if ($profId -ne "all") {
            $profileArg = $profId
        }
        $wslArg = Build-WslArgument -ProfilesArg $profileArg

        $action = New-ScheduledTaskAction -Execute "wsl.exe" -Argument $wslArg

        $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $sched.DowArray -At $atTime

        $settings = New-ScheduledTaskSettingsSet `
            -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
            -StartWhenAvailable `
            -RunOnlyIfNetworkAvailable

        $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($existing) {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
            Write-Host ("  Replaced existing: " + $taskName)
        }

        Register-ScheduledTask `
            -TaskName $taskName `
            -Action   $action `
            -Trigger  $trigger `
            -Settings $settings `
            -RunLevel Limited | Out-Null

        Write-Host ("  OK Registered: " + $taskName) -ForegroundColor Green
        Write-Host ("     wsl.exe " + $wslArg) -ForegroundColor DarkGray
        Write-Host ""
    }
}

function Remove-Tasks {
    $tasks = Get-ScheduledTask -TaskName ($TaskPrefix + "-*") -ErrorAction SilentlyContinue
    if (-not $tasks) {
        Write-Host ("[schedule.ps1] No " + $TaskPrefix + " tasks found.") -ForegroundColor Yellow
        return
    }
    foreach ($task in $tasks) {
        Unregister-ScheduledTask -TaskName $task.TaskName -Confirm:$false
        Write-Host ("  OK Removed: " + $task.TaskName) -ForegroundColor Green
    }
}

function Show-Status {
    $tasks = Get-ScheduledTask -TaskName ($TaskPrefix + "-*") -ErrorAction SilentlyContinue
    if (-not $tasks) {
        Write-Host ("[schedule.ps1] No " + $TaskPrefix + " tasks registered.") -ForegroundColor Yellow
        return
    }
    Write-Host ""
    Write-Host "[schedule.ps1] Registered tasks:" -ForegroundColor Cyan
    foreach ($task in $tasks) {
        $info = Get-ScheduledTaskInfo -TaskName $task.TaskName -ErrorAction SilentlyContinue
        $last = "never"
        $next = "unknown"
        if ($info) {
            if ($info.LastRunTime -gt [datetime]"2000-01-01") {
                $last = $info.LastRunTime.ToString("yyyy-MM-dd HH:mm")
            }
            if ($info.NextRunTime -gt [datetime]"2000-01-01") {
                $next = $info.NextRunTime.ToString("yyyy-MM-dd HH:mm")
            }
        }
        Write-Host ("  Task  : " + $task.TaskName)
        Write-Host ("  State : " + $task.State)
        Write-Host ("  Last  : " + $last)
        Write-Host ("  Next  : " + $next)
        Write-Host ("  Cmd   : " + $task.Actions[0].Arguments) -ForegroundColor DarkGray
        Write-Host ""
    }
}

switch ($Command) {
    "install" { Install-Tasks }
    "remove"  { Remove-Tasks  }
    "status"  { Show-Status   }
}
