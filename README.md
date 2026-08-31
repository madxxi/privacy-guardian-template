# 🛡️ privacy-guardian

Automated personal data exposure scanner for commercial data brokers and
public record sources. Supports multiple profiles, global jurisdictions,
and generates per-person HTML reports with opt-out queues, manual browser
checklists, jurisdiction-aware demand letter citations, email delivery via
msmtp, and automated archive maintenance.

---

## Table of Contents

1. [Setup](#1-setup)
2. [Configuration](#2-configuration)
   - [profiles.yaml](#profilesyaml)
   - [brokers.yaml](#brokersyaml)
   - [notify.yaml](#notifyyaml)
   - [msmtp email setup](#msmtp-email-setup)
   - [Legal frameworks](#legal-frameworks)
3. [Running a scan](#3-running-a-scan)
4. [Output files](#4-output-files)
5. [Sending reports by email](#5-sending-reports-by-email)
6. [Manual browser checklist](#6-manual-browser-checklist)
7. [Archive maintenance](#7-archive-maintenance)
8. [Scheduling](#8-scheduling)
9. [Legal framework reference](#9-legal-framework-reference)
10. [Project structure](#10-project-structure)
11. [Antivirus false positives](#11-antivirus-false-positives)

---

## 1. Setup

```bash
# Extract the project into your repos folder
cd ~/repos
unzip ~/Downloads/privacy-guardian.zip   # or: git clone <your-private-repo>

cd privacy-guardian
bash setup.sh
```

`setup.sh` creates a Python virtual environment at `.venv/` and installs
all dependencies. Run it once after a fresh clone or extract.

After setup, fill in your personal details:

```bash
nano config/profiles.yaml           # your PII — NEVER commit this file
cp config/notify.yaml.example config/notify.yaml
nano config/notify.yaml             # schedule and email settings
```

---

## 2. Configuration

### profiles.yaml

One entry per person. The scanner uses this file to know what to search
for and where to send results. This file is gitignored — never commit it.

```yaml
profiles:

  - id: name                          # short ID used in filenames and CLI
    display_name: "First_Name Last_Name"        # full name shown in reports

    legal_names:
      first: "First_Name"
      middle: "X"
      last:  "Last_Name"
    aliases:                          # name variations also searched for
      - "Alias1 Last_Name"
      - "Alias2 Last_Name"

    # WHERE this profile's report is delivered
    # Completely independent from known_emails below
    notification:
      email: "name.personal@gmail.com"
      method: email                   # email | file_only

    # Drives which legal frameworks are cited in advisories
    jurisdictions:
      - country: "US"
        country_code: "US"
        region: "State_Name"
        region_code: "State_Abb"
        city: "City"
        zip: "ZIP"
        primary: true
      # Add more for dual-jurisdiction situations:
      # - country: "Spain"
      #   country_code: "ES"
      #   region: "Catalonia"
      #   primary: false

    # ALL addresses the scanner should look for on broker sites
    addresses:
      - type: residential
        street: "123 Palmetto Ln"
        city: "City"
        region: "State_Abb"
        zip: "ZIP"
        country: "US"
        current: true
      - type: mailing             # add if different from residential
        street: ""
        city: ""
        region: "State_Abb"
        zip: ""
        country: "US"
        current: true
      # Past addresses help catch older broker listings:
      # - type: residential
      #   street: "456 Old Ave"
      #   city: "Miami"
      #   region: "State_Abb"
      #   zip: "33101"
      #   country: "US"
      #   current: false

    # Phone numbers to search for on broker sites (exposure check only)
    known_phones:
      - number: "954-555-1234"
        type: mobile
      - number: "954-555-5678"
        type: home

    # Email addresses to search for on broker sites
    # DIFFERENT from notification.email above — these are exposure checks
    known_emails:
      - "old.work@example.com"
      - "personal@gmail.com"

    dob_year: "1975"              # year only — helps confirm broker matches
    relative_names:               # used to confirm broker matches
      - "Jane Last_Name"
```

**Key distinction:** `notification.email` is where the scan report is
*sent to*. `known_emails` are addresses that may be *publicly exposed*
on broker sites and are scanned for. They are completely separate fields.

---

### brokers.yaml

The database of known data broker sites. Each entry specifies:

- `name` — display name
- `url` — search URL with `{first}`, `{last}`, `{city}`, `{state}`, `{zip}` placeholders
- `optout_url` — direct link to the removal/opt-out page
- `optout_method` — `form` | `email` | `mail` | `unknown`
- `legal_basis` — applicable law code (`CCPA`, `FCRA`, `EU_GDPR`, etc.)
- `compliant` — `true` if a working opt-out exists; `false` State_Abbags for attorney referral
- `regions` — country/region codes this broker applies to; omit for US-only legacy entries; `GLOBAL` for worldwide
- `notes` — any special instructions

The scanner filters brokers to only those relevant to a profile's
`jurisdictions`, so international brokers are only checked when the
profile has a matching jurisdiction configured.

**YAML quoting note:** Some country codes are reserved words in YAML 1.1
and must be quoted. Always quote values in the `regions` list:

```yaml
regions: ["NO"]     # correct — Norway
regions: [NO]       # wrong — YAML parses this as boolean false
regions: ["US", "CA", "AU"]   # correct multi-region
```

---

### notify.yaml

Created from `config/notify.yaml.example`. Gitignored — never commit it.

```yaml
# ── Scheduler ──────────────────────────────────────────────────────────────
scheduler:
  enabled: true
  day_of_week: "Sunday"           # single day or comma-separated list:
                                  # "Sunday"
                                  # "Monday,Wednesday,Friday"
                                  # "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday"
  hour: 9                         # 24h local time — no inline comment needed
  minute: 0
  email_on_scheduled_run: true    # send email when Task Scheduler fires
  email_on_manual_run: false      # skip email on manual ./scan.sh runs

# ── Email ───────────────────────────────────────────────────────────────────
email:
  enabled: true
  from: "Privacy Guardian"        # display name in From: header
  subject: "Privacy Guardian · {name} · {found} found · {date}"
  method: msmtp
  msmtp:
    config_file: "~/.msmtprc"
    account: privacy-guardian     # named account in ~/.msmtprc (see below)
  report_format: summary          # summary | full
```

**Subject placeholders:** `{name}` `{date}` `{found}` `{blocked}`

**Important:** Avoid inline `#` comments on the `hour:`, `minute:`, and
`day_of_week:` lines — the parser strips them but it is cleaner to omit them.

---

### msmtp email setup

privacy-guardian uses `msmtp` as the mail relay — the same tool as
job-scout. Your existing `~/.msmtprc` is reused; you only need to add
a second named account so the two projects use separate App Passwords.

#### Step 1 — Generate a Gmail App Password for privacy-guardian

Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords),
create a new App Password (name it "privacy-guardian"), and copy the
16-character key.

#### Step 2 — Store it in its own file

```bash
echo "your-16-char-app-password" > ~/.msmtp-privacy.pass
chmod 600 ~/.msmtp-privacy.pass
```

#### Step 3 — Add a second account to `~/.msmtprc`

```
# Existing job-scout account — leave this untouched
account        default
host           smtp.gmail.com
port           587
from           dmynor@gmail.com
user           dmynor@gmail.com
passwordeval   "gpg --quiet --decrypt ~/.msmtp-gmail.gpg 2>/dev/null || cat ~/.msmtp-pass"

# Privacy-guardian account — separate App Password, separate account name
account        privacy-guardian
host           smtp.gmail.com
port           587
from           dmynor@gmail.com
user           dmynor@gmail.com
passwordeval   "cat ~/.msmtp-privacy.pass"
```

Same Gmail address, different App Password, completely independent
accounts. Revoking one does not affect the other.

#### Step 4 — Test before running a scan

```bash
echo "Subject: privacy-guardian test" | \
    msmtp --file ~/.msmtprc --account privacy-guardian dmynor@gmail.com
```

If the test email arrives in your inbox, the configuration is correct.

#### Step 5 — Point notify.yaml at the new account

```yaml
email:
  msmtp:
    config_file: "~/.msmtprc"
    account: privacy-guardian     # matches the account name in ~/.msmtprc
```

---

### Legal frameworks

Stored in `config/legal_frameworks/`. Each file describes the privacy
laws of a jurisdiction — statutes, rights, deadlines, enforcement
agencies, damages, and ready-to-copy citation templates. The scanner
loads whichever files match a profile's `jurisdictions` block automatically.

```
config/legal_frameworks/
├── us_federal.yaml          FCRA, DPPA, GLBA, HIPAA, FTC Act §5
├── us_states/
│   ├── State_Abb.yaml              FIPA, Public Records Act, DPPA implementation
│   ├── CA.yaml              CCPA / CPRA, Shine the Light
│   ├── NY.yaml              SHIELD Act
│   ├── TX.yaml              TDPSA (2024)
│   ├── IL.yaml              BIPA, PIPA
│   └── VA.yaml              CDPA (2023)
└── countries/
    ├── EU_GDPR.yaml         GDPR — covers all EU/EEA member states
    ├── GB.yaml              UK GDPR + DPA 2018
    ├── CA.yaml              PIPEDA (+ Bill C-27 pending)
    ├── AU.yaml              Privacy Act 1988 + 2024 amendments
    ├── BR.yaml              LGPD
    ├── MX.yaml              LFPDPPP (ARCO rights)
    └── SG.yaml              PDPA 2012 (amended 2021)
```

To add a new state or country: create a YAML file following the existing
structure, then add the code to `COUNTRY_FRAMEWORK_MAP` or
`US_STATE_FRAMEWORK_MAP` in `scanner/legal_advisor.py`.

---

## 3. Running a scan

```bash
bash scan.sh                          # all profiles
bash scan.sh --verbose                # with debug logging
```

### Selecting profiles

All of the following formats are equivalent and can be combined:

```bash
bash scan.sh --profiles all           # explicit — same as omitting
bash scan.sh --profiles name          # one profile by ID
bash scan.sh --profiles name name2   # space-separated
bash scan.sh --profiles name,name2   # comma-separated
bash scan.sh -p name -p name2        # repeated State_Abbag
bash scan.sh -p name,name2 wife      # mixed
```

Profile IDs are defined in `config/profiles.yaml` under the `id:` field.

### Additional State_Abbags

```bash
bash scan.sh --no-email               # skip email delivery this run
bash scan.sh --no-archive             # skip archive maintenance this run
bash scan.sh --scheduled              # mark as scheduled run (see email settings)
bash scan.sh -p name --no-email --verbose   # State_Abbags combine freely
```

### What the scanner does

For each selected profile the scanner:

1. Loads all applicable legal frameworks based on `jurisdictions`
2. Builds a search corpus from all addresses, phones, emails, and name variants
3. Checks each relevant data broker via HTTP GET
4. Detects matches by looking for name tokens, city, phone digits, email
   addresses, and partial street names in the page content
5. For each FOUND result: generates a jurisdiction-aware legal advisory
   and a ready-to-copy demand letter citation block
6. Checks State_Name public record sources separately (property, courts, DMV, voter)
7. Writes all output files and sends email

**BLOCKED results are normal.** Most major brokers (Whitepages,
BeenVerified, Intelius, TruthFinder, FastPeopleSearch, etc.) sit behind
CloudState_Abbare and return HTTP 403. BLOCKED means the site is live and
understood your request — it just won't serve content to an automated
client. The manual checklist (section 6) handles these.

---

## 4. Output files

Every output file is per-profile. No file contains data from more than
one person.

```
outputs/
├── reports/
│   ├── report_name_20260830_003134.html
│   ├── report_name2_20260830_003134.html
│   ├── manual_checklist_name_20260830_003134.html
│   └── manual_checklist_name2_20260830_003134.html
├── optout_queue/
│   └── scan_20260830/
│       ├── optout_name.txt
│       └── optout_name2.txt
├── archive/                        ← older reports moved here automatically
│   ├── report_name_20260823.html
│   └── report_name_20260801.html.gz
├── scan_history.db                 ← SQLite: scan history + checklist state (checkbox/date/notes)
│   └── checklist_state_<id>.json   ← Save Progress export; drop here to carry notes to next scan
│   └── checklist_state_<id>.json.imported  ← renamed after auto-import
logs/
├── scan_20260830.log
├── cron.log                        ← output from scheduled Task Scheduler runs
└── scan_20260801.log.gz            ← compressed after 30 days
```

**HTML report** — open in any browser. Contains broker scan results,
match signals, legal advisories, and expandable demand letter citation
blocks for each FOUND entry.

**Manual checklist** — browser-interactive checklist for blocked brokers.
See section 6.

**Opt-out queue** — plain-text version of all FOUND entries with full
legal advisory and citation letter text. Copy-paste friendly for drafting
formal removal requests.

**Scan history** — SQLite database. Query directly with `sqlite3`:

```bash
sqlite3 outputs/scan_history.db \
  "SELECT broker_name, status, scan_date
   FROM scan_events
   WHERE profile_id='name'
   ORDER BY scan_date DESC LIMIT 20;"
```

---

## 5. Sending reports by email

### Automatic (after every scan)

Email is sent automatically at the end of each scan, controlled by
`notify.yaml`. Each profile receives only its own report at its own
`notification.email` address. The email subject is:

```
Privacy Guardian · First_Name Last_Name · 2 found · Sun Aug 30 2026
```

Attachments per profile email:
- `report_<id>_<timestamp>.html` — full HTML report
- `manual_checklist_<id>_<timestamp>.html` — browser checklist (omitted if nothing was blocked)

### email_on_scheduled_run vs email_on_manual_run

```yaml
scheduler:
  email_on_scheduled_run: true    # email fires when Task Scheduler triggers the scan
  email_on_manual_run: false      # no email when you run bash scan.sh manually
```

This mirrors the job-scout pattern — daily/weekly automated runs email
you, ad-hoc manual runs do not (unless you explicitly add `--scheduled`
or State_Abbip the State_Abbag).

### On-demand: send any existing report without rescanning

You must specify the profile ID so the tool knows which notification
address to use. It never sends one profile's files to another profile.

```bash
# Send one profile's report
python3 -m reporter.notifier \
    --profile name \
    --report outputs/reports/report_name_20260830_003134.html

# Send report + checklist together
python3 -m reporter.notifier \
    --profile name \
    --report outputs/reports/report_name_20260830_003134.html \
    --checklist outputs/reports/manual_checklist_name_20260830_003134.html

# Send a different profile's report
python3 -m reporter.notifier \
    --profile name2 \
    --report outputs/reports/report_name2_20260830_003134.html
```

### Send only the checklist

Pass the checklist file as `--report`:

```bash
python3 -m reporter.notifier \
    --profile name \
    --report outputs/reports/manual_checklist_name_20260830_003134.html
```

### Skip email for one run

```bash
bash scan.sh --no-email
bash scan.sh -p name --no-email
```

---

## 6. Manual browser checklist

The checklist HTML file (`manual_checklist_<id>_<timestamp>.html`) is a
self-contained interactive page. Open it in your regular browser —
Chrome, Firefox, Edge, or Safari. No internet connection is needed to
use the checklist UI itself.

### What it contains

One row per broker that returned BLOCKED or ERROR during the automated
scan. Each row has:

- **Done checkbox** — mark when you have submitted the opt-out request.
  The row turns green when checked.
- **Opt-out date picker** — auto-fills today's date when you check the
  box; adjust to the actual date you submitted if different. Unlocks
  when the checkbox is checked; clears if you uncheck.
- **Follow-up reminder** — calculated 35 days after the opt-out date.
  Shows orange ("📅 Follow-up by Apr 15") while pending, turns red
  ("⚠️ Follow-up overdue!") once that date passes — your reminder to
  revisit the broker and confirm your data was actually removed.
- **Notes field** — a free-text area to log follow-up actions for that
  broker. Use this for anything that needs recording: call reference
  numbers, BBB complaint IDs, attorney referral dates, escalation steps,
  responses received, or a note that the opt-out form is broken and a
  call was needed instead. Notes are always editable regardless of
  whether the checkbox is checked.
- **📞 Phone button** — shown in purple when the broker has a known
  support number. Tapping or clicking it opens your phone dialer directly.
  Use this when the online opt-out form is failing or deliberately broken.
- **Search button** — opens the broker's search page in a new tab with
  your name pre-filled in the URL.
- **Opt-out button** — opens the broker's removal page directly.
- **Law badge** — applicable legal basis (`CCPA`, `FCRA`, `EU_GDPR`, etc.)
- **NO OPT-OUT badge** — shown in red for brokers with no removal
  process; refer these to your attorney.
- **Broker Notes** — the static notes from `brokers.yaml` for that
  entry (e.g. "Phone verification required", "Same PeopleConnect umbrella
  as Intelius"). These are read-only hints, distinct from your personal notes.

### What state is saved and carried forward

All three pieces of interactive state persist across sessions and across
weekly scans:

| Field | Saved instantly | Carried to next scan |
|-------|----------------|---------------------|
| ✅ Checkbox (done) | localStorage | Yes — pre-fills on next checklist |
| 📅 Opt-out date | localStorage | Yes — pre-fills on next checklist |
| 📝 Notes | localStorage | Yes — pre-fills on next checklist |

**Within the same file:** all state saves to your browser's `localStorage`
automatically on every change. Closing and reopening the same HTML file
restores everything exactly as you left it.

**Across weekly scans** (carrying state to a newly generated checklist):
state is persisted to SQLite (`outputs/scan_history.db`) and injected
into the new HTML file at build time, so the new checklist opens with
your previous checkbox, date, and notes already filled in — no manual
copying needed.

### Saving progress between scans

Click **💾 Save Progress** at the top of the checklist. This downloads a
file named `checklist_state_<profile_id>.json` to your Downloads folder.

```
checklist_state_name.json
checklist_state_name2.json
```

Move or copy that file into your `outputs/` directory:

```bash
mv ~/Downloads/checklist_state_name.json ~/repos/privacy-guardian/outputs/
```

On the next scan run, privacy-guardian automatically detects and imports
this file into the database before building the new checklist. After
import, the file is renamed to `checklist_state_name.json.imported` so
it is not re-processed on subsequent scans.

**You must do this before the next scan runs.** If the scan generates a
new checklist before you save and move the file, the new checklist will
be pre-populated from whatever was previously in the database (which may
be empty or from an older run). Your localStorage state in the old file
is still there — open the old file, click Save Progress, move the file,
and re-run the scan to regenerate with the correct state.

### What happens when a broker is no longer blocked

If a broker that previously appeared in your checklist (with notes and a
date) starts returning results in the automated scan instead of being
blocked — meaning the scanner got through CloudState_Abbare — it will no longer
appear in the new checklist. This is correct behavior: the scanner handled
it automatically. Its state (checkbox, date, notes) remains in the database
permanently and can be queried:

```bash
sqlite3 outputs/scan_history.db   "SELECT broker_name, optout_date, followup_notes
   FROM checklist_state
   WHERE profile_id='name'
   ORDER BY last_updated DESC;"
```

### Recommended workState_Abbow

1. Open the checklist in a private/incognito browser window
2. Work through 5–10 brokers per session to avoid rate limits
3. For each broker:
   - Click **Search** and look for your listing
   - Click **Opt-out** and submit their removal form
   - If the form fails or is broken: click the **📞 phone button** to call
   - Check the box — the date auto-fills to today; adjust if needed
   - Type any relevant notes in the Notes field (reference numbers, outcome, next step)
4. For brokers marked **NO OPT-OUT**: screenshot the page, note it in the
   Notes field, and forward to your attorney with the legal advisory from
   the main HTML report
5. Before the weekly scan runs again: click **💾 Save Progress** and move
   the downloaded JSON file into `outputs/`

### Adding a phone number for a broker that doesn't have one

If you call a broker and discover their support number, add it to
`brokers.yaml` under the `phone:` field for that entry:

```yaml
  - name: "Radaris"
    ...
    phone: "(800) 555-1234"    # ← add the number here
```

It will appear as a purple 📞 button in the next generated checklist.
Brokers with a blank `phone: ""` show "—" in that column.

---

## 7. Archive maintenance

The archiver runs automatically at the end of every scan. It can also
be run manually at any time.

### How it works

| Age of file | Action |
|-------------|--------|
| > 7 days | Moved from `outputs/reports/` to `outputs/archive/` |
| > 30 days | Compressed with gzip (`.html` → `.html.gz`) |
| > 120 days | Permanently deleted |

The same thresholds apply to log files in `logs/`. Opt-out queue
directories (`outputs/optout_queue/scan_YYYYMMDD/`) are moved to
`outputs/archive/` after 7 days.

Thresholds are defined as constants at the top of `reporter/archiver.py`
and can be adjusted:

```python
ARCHIVE_AFTER_DAYS  = 7
COMPRESS_AFTER_DAYS = 30
DELETE_AFTER_DAYS   = 120
```

### Manual commands

```bash
# Show current age and projected fate of every report and log
python3 -m reporter.archiver --status

# Force an archive cycle now (without running a scan)
python3 -m reporter.archiver --run
```

`--status` output example:

```
────────────────────────────────────────────────────────────
FILE                                              AGE  STATUS
────────────────────────────────────────────────────────────
REPORTS (active):
  report_name_20260830_003134.html                  0d  ✅ current
  report_name2_20260830_003134.html                0d  ✅ current

ARCHIVE:
  report_name_20260823_120000.html                  7d  📦 ARCHIVE (next run)
  report_name_20260723_120000.html                 37d  🟡 COMPRESS (next run)
  report_name_20260401_120000.html                149d  🔴 DELETE (next run)

LOGS:
  scan_20260830.log                                 0d  ✅ current
  scan_20260723.log.gz                             37d  🟡 COMPRESS (next run)

Thresholds: archive after 7d | compress after 30d | delete after 120d
────────────────────────────────────────────────────────────
```

### Skip archive for a single run

```bash
bash scan.sh --no-archive
```

---

## 8. Scheduling

Privacy Guardian uses Windows Task Scheduler (via WSL), the same
approach as job-scout. No cron required. The schedule is configured
in `config/notify.yaml` and the task is registered by running a single
command from your WSL terminal.

### Configure the schedule in notify.yaml

```yaml
scheduler:
  enabled: true
  day_of_week: "Sunday"             # see formats below
  hour: 9                           # 24h local time
  minute: 0
  email_on_scheduled_run: true
  email_on_manual_run: false
```

**day_of_week formats:**

```yaml
day_of_week: "Sunday"                                              # one day
day_of_week: "Monday,Wednesday,Friday"                             # several days
day_of_week: "Monday,Tuesday,Wednesday,Thursday,Friday"            # weekdays
day_of_week: "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday"  # daily
```

Valid values (case-sensitive): `Sunday` `Monday` `Tuesday` `Wednesday`
`Thursday` `Friday` `Saturday`

### Register the task (from your WSL terminal)

All scheduling commands run from the WSL terminal inside the project
directory. No separate PowerShell window needed — `scan.sh` invokes
`powershell.exe` via `wslpath` automatically.

```bash
# Register — all profiles, schedule from notify.yaml
bash scan.sh schedule install

# Register — specific profiles only
bash scan.sh schedule install -Profiles "name,name2"

# Specify WSL distro explicitly (default is Ubuntu-20.04)
bash scan.sh schedule install -WslDistro "Ubuntu-22.04"

# Check what is registered and when it will next run
bash scan.sh schedule status

# Remove all privacy-guardian tasks
bash scan.sh schedule remove
```

After `install`, re-run `status` to confirm:

```
[schedule.ps1] Registered tasks:
  Task  : privacy-guardian-all
  State : Ready
  Last  : never
  Next  : 2026-09-06 09:00
  Cmd   : -d Ubuntu-20.04 -- bash -lc "cd /home/name/repos/privacy-guardian && bash scan.sh --scheduled >> /home/name/repos/privacy-guardian/logs/cron.log 2>&1"
```

- `State: Ready` — Windows has it armed
- `Next:` — confirms the correct upcoming date and time
- `Cmd:` — verify the distro name and project path are correct

### How the trigger works

```
Windows Task Scheduler
  fires at configured day/time
    → wsl.exe -d Ubuntu-20.04 -- bash -lc "cd /home/name/repos/... && bash scan.sh --scheduled >> logs/cron.log 2>&1"
      → scan.sh activates the venv and calls main.py --scheduled
        → scans run, reports generated, emails sent, archive maintained
          → all output appended to logs/cron.log
```

Windows Task Scheduler runs in the background at all times. You do not
need WSL running, a terminal open, or any manual action — Windows wakes
WSL at the scheduled time.

### Update the schedule

Edit `notify.yaml`, then re-run install — it replaces the existing task:

```bash
nano config/notify.yaml             # change day_of_week or hour
bash scan.sh schedule remove        # remove old task
bash scan.sh schedule install       # register with new schedule
bash scan.sh schedule status        # confirm
```

### Test the full chain before the first scheduled run

```bash
# Runs exactly what Task Scheduler would run, skipping email
bash scan.sh --scheduled --verbose --no-email
```

### Trigger manually from Windows Task Scheduler

If you want to fire it immediately from Windows without waiting for the
schedule (e.g. to test), open Task Scheduler, find `privacy-guardian-all`
under Task Scheduler Library, right-click → Run. Or from PowerShell:

```powershell
Start-ScheduledTask -TaskName "privacy-guardian-all"
```

---

## 9. Legal framework reference

### US Federal (applied to all US-resident profiles)

| Code | Law | Key Rights | Damages |
|------|-----|-----------|---------|
| `FCRA` | Fair Credit Reporting Act | Dispute inaccurate data; 30-day response | $100–$1,000/violation + attorney fees; private right of action |
| `DPPA` | Driver's Privacy Protection Act | DMV data cannot be sold for marketing | $2,500 min/violation; federal crime |
| `GLBA` | Gramm-Leach-Bliley Act | Opt out of financial data sharing | CFPB enforcement; no private right of action |
| `FTCA_5` | FTC Act Section 5 | Deceptive data practices | FTC enforcement |
| `HIPAA` | Health Insurance Portability Act | Health data protection | HHS OCR enforcement |

### US States

| State | Law | Key Rights | Damages |
|-------|-----|-----------|---------|
| `State_Abb` | FIPA (§ 501.171) | Breach notification 30 days | $500K/breach; AG enforcement |
| `State_Abb` | Public Records Act (§ 119.071) | Address suppression for protected occupations | AG enforcement |
| `State_Abb` | DPPA implementation (§ 322.142) | Supplements federal DPPA | DHSMV + AG enforcement |
| `CA` | CCPA / CPRA | Delete, correct, opt-out of sale, portability | $100–$750/violation; private right of action |
| `CA` | Shine the Light (§ 1798.83) | List third parties receiving data for marketing | AG enforcement |
| `NY` | SHIELD Act (§ 899-bb) | Breach notification; data security | $5,000/violation; AG enforcement |
| `TX` | TDPSA (2024) | Delete, correct, opt-out of sale | $7,500/violation; AG enforcement |
| `IL` | BIPA (740 ILCS 14) | Consent for biometrics; destruction right | $1,000–$5,000/violation; private right of action |
| `VA` | CDPA (2023) | Delete, correct, opt-out of sale and profiling | $7,500/violation; AG enforcement |

### International

| Region | Law | Response Deadline | Damages |
|--------|-----|-------------------|---------|
| EU/EEA | GDPR | 1 month | €20M or 4% global turnover |
| UK | UK GDPR + DPA 2018 | 1 month | £17.5M or 4% global turnover |
| Canada | PIPEDA | 30 days | OPC + Federal Court |
| Australia | Privacy Act 1988 (APPs) | 30 days | AUD 50M; OAIC |
| Brazil | LGPD | 15 days | R$50M/violation; ANPD |
| Mexico | LFPDPPP (ARCO) | 20 business days | INAI enforcement |
| Singapore | PDPA 2012 | 30 business days | SGD 1M or 10% local turnover |

> **Disclaimer:** All legal advisories and citation templates are
> informational only. Consult a licensed attorney for case-specific action.

---

## 10. Project structure

```
privacy-guardian/
│
├── config/
│   ├── profiles.yaml               ← YOUR PII — gitignored, never commit
│   ├── brokers.yaml                ← broker database (safe to commit)
│   ├── notify.yaml                 ← schedule + email settings — gitignored
│   ├── notify.yaml.example         ← template — safe to commit
│   └── legal_frameworks/
│       ├── us_federal.yaml
│       ├── us_states/
│       │   ├── State_Abb.yaml  CA.yaml  NY.yaml  TX.yaml  IL.yaml  VA.yaml
│       └── countries/
│           ├── EU_GDPR.yaml  GB.yaml  CA.yaml  AU.yaml
│           └── BR.yaml  MX.yaml  SG.yaml
│
├── scanner/
│   ├── main.py                     ← orchestrator; entry point for scan.sh
│   ├── broker_scanner.py           ← HTTP scanning of commercial brokers
│   ├── public_records.py           ← State_Abb public record sources
│   ├── legal_advisor.py            ← loads frameworks, generates advisories
│   └── __init__.py
│
├── reporter/
│   ├── report_builder.py           ← one HTML report per profile
│   ├── manual_checklist.py         ← one interactive checklist per profile
│   ├── checklist_state.py          ← SQLite persistence for checklist state (checkbox/date/notes)
│   ├── notifier.py                 ← msmtp email delivery; on-demand CLI
│   ├── archiver.py                 ← age-based archive/compress/delete
│   ├── tracker.py                  ← SQLite scan history
│   └── __init__.py
│
├── outputs/                        ← gitignored; all generated files
│   ├── reports/                    ← current HTML reports and checklists
│   ├── optout_queue/               ← plain-text opt-out queues by scan date
│   ├── archive/                    ← older reports (auto-managed)
│   └── scan_history.db
│
├── logs/                           ← gitignored
│   ├── scan_YYYYMMDD.log           ← per-run log
│   └── cron.log                    ← output from Task Scheduler runs
│
├── scan.sh                         ← main entry point for all operations
├── schedule.ps1                    ← Windows Task Scheduler registration
├── setup.sh                        ← one-time environment setup
├── requirements.txt
├── .gitignore
└── README.md
```

### scan.sh subcommands

```bash
bash scan.sh [scan State_Abbags]            # run a scan (default)
bash scan.sh schedule install        # register Windows Task Scheduler task
bash scan.sh schedule status         # show registered tasks and next run time
bash scan.sh schedule remove         # remove all privacy-guardian tasks
```

### Adding a new state or country framework

1. Create `config/legal_frameworks/us_states/<ST>.yaml` or
   `config/legal_frameworks/countries/<CC>.yaml` following the
   existing file structure (copy `State_Abb.yaml` or `EU_GDPR.yaml` as a template)
2. Add the code to `US_STATE_FRAMEWORK_MAP` or `COUNTRY_FRAMEWORK_MAP`
   in `scanner/legal_advisor.py`
3. Add the matching `country_code` or `region_code` to `jurisdictions:`
   in `profiles.yaml` for any profile that should use it
4. The framework loads automatically on the next scan

### gitignored files (never commit these)

```
config/profiles.yaml
config/notify.yaml
outputs/
logs/
*.db
.venv/
```

---

## 11. Antivirus false positives

### Why it happens

The HTML files generated by privacy-guardian — particularly the manual
browser checklist — will occasionally be State_Abbagged by antivirus or endpoint
security software as suspicious or malicious. This is a **false positive**.
No malicious code exists in any file generated by this project.

The false positive is triggered by a combination of factors that heuristic
scanners associate with browser-based malware:

- **JavaScript using `localStorage`** — the checklist saves checkbox and
  date state in the browser. AV heuristics associate `localStorage` read/write
  with credential-harvesting phishing pages.
- **Looping DOM manipulation** — the progress bar and row state updates
  use `querySelectorAll` and `forEach` loops, a pattern common in both
  legitimate web apps and browser-based keyloggers.
- **Embedded personal data** — your name and URLs to data broker sites
  appear inline in the HTML. Some brokers are on reputation blocklists,
  and their URLs being present in a local file can trigger URL-based
  detection rules.
- **Self-contained single-file HTML** — phishing kits are commonly
  distributed as self-contained HTML files to avoid needing a server.
  The checklist is self-contained for the same legitimate reason: it
  needs to work ofState_Abbine with no dependencies.

All JavaScript in the generated files comes directly from
`reporter/manual_checklist.py`, which you can inspect in full. It does
exactly three things: saves/loads checkbox state, updates a progress bar,
and calculates follow-up reminder dates.

### What to do when a file is State_Abbagged

If your antivirus quarantines or deletes a generated report or checklist:

1. **Restore the file from quarantine** — most AV software keeps a copy.
   In Windows Security / Defender: open Windows Security → Virus & threat
   protection → Protection history → find the quarantined item → Restore.

2. **Mark it as safe / add an exception** for that specific file so it
   is not quarantined again.

3. **Add a folder exclusion** (recommended, see below) so future scan
   outputs are never blocked.

### Adding antivirus exclusions

The right approach is to exclude the `outputs/` and `logs/` directories
inside the project, since all generated files live there. These are the
only directories that contain files created at runtime — the Python source
files and YAML configs are never State_Abbagged.

#### Windows Defender / Windows Security (most common)

```
1. Open Windows Security
2. Virus & threat protection → Manage settings
3. Scroll to Exclusions → Add or remove exclusions
4. Click Add an exclusion → Folder
5. Navigate to and select:
       \\wsl.localhost\Ubuntu-20.04\home\name\repos\privacy-guardian\outputs
6. Repeat for:
       \\wsl.localhost\Ubuntu-20.04\home\name\repos\privacy-guardian\logs
```

Or add both exclusions at once from PowerShell (run as Administrator):

```powershell
Add-MpPreference -ExclusionPath "\\wsl.localhost\Ubuntu-20.04\home\name\repos\privacy-guardian\outputs"
Add-MpPreference -ExclusionPath "\\wsl.localhost\Ubuntu-20.04\home\name\repos\privacy-guardian\logs"
```

Verify the exclusions were added:

```powershell
Get-MpPreference | Select-Object -ExpandProperty ExclusionPath
```

#### Malwarebytes

```
1. Open Malwarebytes → Settings → Allow List
2. Click Add → Allow a File or Folder
3. Select the outputs\ folder inside the project
4. Repeat for the logs\ folder
```

#### Norton / Symantec

```
1. Open Norton → Settings → Antivirus → Scans and Risks
2. Exclusions / Low Risks → Configure (next to Items to Exclude from Scans)
3. Add → Select the outputs\ folder
```

#### ESET

```
1. Open ESET → Setup → Advanced Setup (F5)
2. Detection Engine → Exclusions → Add
3. Browse to the outputs\ folder and add it
```

#### Kaspersky

```
1. Open Kaspersky → Settings → Threats and Exclusions
2. Manage Exclusions → Add
3. Browse to and select the outputs\ folder
4. Scope: All components → Save
```

#### Trend Micro

```
1. Open Trend Micro → Settings → Exception List
2. Add the full path to the outputs\ folder
```

### Why excluding outputs\ is safe

The `outputs/` directory contains only files generated by privacy-guardian
itself during a scan — HTML reports, text opt-out queues, and the SQLite
history database. No executable code, no downloaded content, and no files
from external sources ever land in that directory. The Python source that
generates them is in `scanner/` and `reporter/`, which do not need to be
excluded.

If you are ever uncertain whether a State_Abbagged file is legitimate, you can
verify it by checking its modification timestamp against your last scan
run in `logs/scan_YYYYMMDD.log`, and by inspecting the file contents —
every generated HTML file starts with a standard `<!DOCTYPE html>` header
and contains only the HTML/CSS/JS templates defined in
`reporter/manual_checklist.py` or `reporter/report_builder.py`.

### Reporting a false positive to your AV vendor

If you want to help reduce false positives for others, most vendors have
a submission portal:

- **Microsoft Defender** — [microsoft.com/wdsi/filesubmission](https://www.microsoft.com/wdsi/filesubmission) — select "This is a clean file that was incorrectly detected"
- **Malwarebytes** — [forums.malwarebytes.com](https://forums.malwarebytes.com) → False Positives board
- **Norton** — [symantec.com/security-center/submit](https://www.norton.com/submit-security)
- **ESET** — [support.eset.com/kb141](https://support.eset.com/kb141)
- **Kaspersky** — [opentip.kaspersky.com](https://opentip.kaspersky.com)

Submitting a false positive helps the vendor tune their heuristics so the
file type is no longer State_Abbagged for future users.
