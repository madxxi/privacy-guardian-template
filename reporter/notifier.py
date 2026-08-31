"""
notifier.py
Sends each profile's report exclusively to that profile's notification address.
Uses msmtp as the mail relay (same pattern as job-scout), reading account
config from ~/.msmtprc and the API key from ~/.msmtp-pass.

No smtplib — mail is handed off to the msmtp binary via subprocess,
exactly as job-scout does it.

Subject placeholders: {name} {date} {found} {blocked}
"""
from __future__ import annotations

import base64
import logging
import subprocess
import tempfile
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent / "config"


# ── Config loading ────────────────────────────────────────────────────────────

def _load_notify_config() -> dict:
    path = CONFIG_DIR / "notify.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"notify.yaml not found at {path}. "
            "Copy config/notify.yaml.example and fill in your settings."
        )
    with open(path) as f:
        return yaml.safe_load(f)


def _label(profile: dict) -> str:
    names = profile.get("legal_names", {})
    return (
        profile.get("display_name") or
        f"{names.get('first', '')} {names.get('last', '')}".strip() or
        profile["id"]
    )


# ── Subject line ──────────────────────────────────────────────────────────────

def _build_subject(template: str, profile_label: str, pr: dict) -> str:
    broker_rows = pr.get("broker_results", [])
    found   = sum(1 for r in broker_rows if r.status == "FOUND")
    blocked = sum(1 for r in broker_rows if r.status == "BLOCKED")
    date    = datetime.now().strftime("%a %b %d %Y")
    return (
        template
        .replace("{name}",    profile_label)
        .replace("{date}",    date)
        .replace("{found}",   str(found))
        .replace("{blocked}", str(blocked))
    )


# ── Email body ────────────────────────────────────────────────────────────────

def _build_summary(pr: dict) -> str:
    """Plain-text summary for one profile — no other profile's data included."""
    profile     = pr["profile"]
    broker_rows = pr.get("broker_results", [])
    pub_rows    = pr.get("pub_results",    [])

    found   = [r for r in broker_rows if r.status == "FOUND"]
    blocked = [r for r in broker_rows if r.status == "BLOCKED"]
    clear   = [r for r in broker_rows if r.status == "NOT_FOUND"]

    lines = [
        f"Privacy Guardian Scan Summary",
        f"Scan time : {pr.get('scan_time', 'unknown')}",
        "",
        "COMMERCIAL BROKERS",
        f"  Found   : {len(found)}",
        f"  Clear   : {len(clear)}",
        f"  Blocked : {len(blocked)}  (open attached checklist in browser)",
        "",
    ]

    if found:
        lines.append("FOUND — opt-out action required:")
        for r in found:
            flag = "  ⚠ NO OPT-OUT — ATTORNEY" if not r.compliant else ""
            lines += [
                f"  • {r.broker_name}{flag}",
                f"    Opt-out : {r.optout_url or 'N/A'}",
            ]
        lines.append("")

    if blocked:
        lines.append("BLOCKED — open the attached manual checklist:")
        for r in blocked[:10]:          # cap inline list at 10
            lines.append(f"  • {r.broker_name}")
        if len(blocked) > 10:
            lines.append(f"  … and {len(blocked) - 10} more (see checklist)")
        lines.append("")

    pub_found = [r for r in pub_rows if r.status == "FOUND"]
    if pub_found:
        lines.append("PUBLIC RECORD SOURCES (reachable):")
        for r in pub_found:
            masking = "Masking available" if r.masking_available else "No general-public masking"
            lines.append(f"  • {r.source_name} — {masking}")
        lines.append("")

    lines += [
        "Full HTML report and manual checklist are attached.",
        "Legal advisories are informational — consult your attorney for case-specific action.",
        "",
        "— privacy-guardian",
    ]
    return "\n".join(lines)


def _build_full(pr: dict) -> str:
    """Summary + full opt-out list inline."""
    summary = _build_summary(pr)
    found   = [r for r in pr.get("broker_results", []) if r.status == "FOUND"]
    if not found:
        return summary

    lines = [summary, "", "=" * 60, "FULL OPT-OUT LIST", "=" * 60, ""]
    for r in sorted(found, key=lambda x: x.broker_name):
        flag = " ⚠ NO OPT-OUT — ATTORNEY REFERRAL" if not r.compliant else ""
        lines += [
            f"Broker    : {r.broker_name}{flag}",
            f"Signals   : {', '.join(r.match_signals)}",
            f"Legal     : {r.legal_basis}",
            f"Opt-out   : {r.optout_url or 'None'}",
            f"Method    : {r.optout_method}",
            "",
        ]
    return "\n".join(lines)


# ── MIME message builder ──────────────────────────────────────────────────────

def _build_mime(
    from_display:   str,
    to_addr:        str,
    subject:        str,
    body:           str,
    report_path:    Path,
    checklist_path: Path | None,
) -> MIMEMultipart:
    msg = MIMEMultipart("mixed")
    msg["From"]    = from_display
    msg["To"]      = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for path in [report_path, checklist_path]:
        if path and path.exists():
            with open(path, "rb") as f:
                part = MIMEApplication(f.read(), Name=path.name)
            part["Content-Disposition"] = f'attachment; filename="{path.name}"'
            msg.attach(part)
            log.debug(f"Attached: {path.name}")
        elif path:
            log.warning(f"Attachment not found, skipping: {path}")

    return msg


# ── msmtp delivery ────────────────────────────────────────────────────────────

def _send_via_msmtp(msg: MIMEMultipart, to_addr: str, msmtp_cfg: dict) -> bool:
    """
    Hand the message off to msmtp, exactly as job-scout does.
    Returns True on success.
    """
    config_file = Path(msmtp_cfg.get("config_file", "~/.msmtprc")).expanduser()
    account     = msmtp_cfg.get("account", "default")

    cmd = [
        "msmtp",
        "--file", str(config_file),
        "--account", account,
        "--read-envelope-from",
        to_addr,
    ]

    raw = msg.as_bytes()

    try:
        result = subprocess.run(
            cmd,
            input=raw,
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            log.info(f"✅ msmtp → {to_addr}  [{msg['Subject']}]")
            return True
        else:
            err = result.stderr.decode(errors="replace").strip()
            log.error(f"msmtp failed (rc={result.returncode}): {err}")
            return False
    except FileNotFoundError:
        log.error(
            "msmtp binary not found. Install with: sudo apt install msmtp"
        )
        return False
    except subprocess.TimeoutExpired:
        log.error("msmtp timed out after 30 seconds")
        return False
    except Exception as exc:
        log.error(f"Unexpected msmtp error: {exc}")
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def send_reports(
    all_results:     list[dict],
    report_paths:    dict[str, Path],
    checklist_paths: dict[str, Path],
    scheduled:       bool = False,
) -> None:
    """
    Send each profile's report only to that profile's notification email.
    scheduled=True  → honours email_on_scheduled_run setting
    scheduled=False → honours email_on_manual_run setting
    """
    try:
        cfg = _load_notify_config()
    except FileNotFoundError as e:
        log.warning(f"Email not sent: {e}")
        return

    email_cfg = cfg.get("email", {})
    if not email_cfg.get("enabled", False):
        log.info("Email disabled in notify.yaml — skipping.")
        return

    sched_cfg = cfg.get("scheduler", {})
    if scheduled and not sched_cfg.get("email_on_scheduled_run", True):
        log.info("email_on_scheduled_run=false — skipping email.")
        return
    if not scheduled and not sched_cfg.get("email_on_manual_run", False):
        log.info("email_on_manual_run=false — skipping email for manual run.")
        return

    method      = email_cfg.get("method", "msmtp")
    msmtp_cfg   = email_cfg.get("msmtp", {})
    from_disp   = email_cfg.get("from", "Privacy Guardian")
    subj_tmpl   = email_cfg.get("subject",
                    "Privacy Guardian · {name} · {found} found · {date}")
    report_fmt  = email_cfg.get("report_format", "summary")

    for pr in all_results:
        profile = pr["profile"]
        pid     = profile["id"]
        notif   = profile.get("notification", {})
        to_addr = notif.get("email", "").strip()
        notif_method = notif.get("method", "email")

        if notif_method != "email" or not to_addr:
            log.debug(f"Skipping email for {pid} (method={notif_method}, addr={to_addr or 'not set'})")
            continue

        report_path    = report_paths.get(pid)
        checklist_path = checklist_paths.get(pid)

        if not report_path:
            log.warning(f"No report file for profile {pid} — skipping email")
            continue

        name    = _label(profile)
        subject = _build_subject(subj_tmpl, name, pr)
        body    = _build_full(pr) if report_fmt == "full" else _build_summary(pr)

        msg = _build_mime(
            from_display   = from_disp,
            to_addr        = to_addr,
            subject        = subject,
            body           = body,
            report_path    = report_path,
            checklist_path = checklist_path,
        )

        if method == "msmtp":
            _send_via_msmtp(msg, to_addr, msmtp_cfg)
        else:
            log.error(f"Unsupported email method '{method}' — only msmtp is supported")


def send_report_on_demand(
    profile_id:     str,
    report_path:    Path,
    checklist_path: Path | None = None,
) -> None:
    """
    Send one profile's report on demand without running a new scan.
    Reads notify.yaml for msmtp settings and profiles.yaml for the address.
    Ignores email_on_manual_run — on-demand always sends if email is enabled.
    """
    try:
        cfg = _load_notify_config()
    except FileNotFoundError as e:
        log.error(str(e))
        return

    email_cfg = cfg.get("email", {})
    if not email_cfg.get("enabled", False):
        log.error("Email is disabled in notify.yaml — set enabled: true to send.")
        return

    profiles_path = CONFIG_DIR / "profiles.yaml"
    with open(profiles_path) as f:
        profiles_cfg = yaml.safe_load(f)

    profile = next(
        (p for p in profiles_cfg["profiles"] if p["id"] == profile_id), None
    )
    if not profile:
        log.error(f"Profile ID '{profile_id}' not found in profiles.yaml")
        return

    to_addr = profile.get("notification", {}).get("email", "").strip()
    if not to_addr:
        log.error(f"No notification.email set for profile '{profile_id}'")
        return

    method    = email_cfg.get("method", "msmtp")
    msmtp_cfg = email_cfg.get("msmtp", {})
    from_disp = email_cfg.get("from", "Privacy Guardian")
    name      = _label(profile)
    scan_date = datetime.now().strftime("%a %b %d %Y")
    subject   = f"Privacy Guardian · {name} · On-demand report · {scan_date}"

    body = (
        f"On-demand report delivery for {name}.\n\n"
        f"Report   : {report_path.name}\n"
        f"See the attached HTML file(s) for full details.\n\n"
        f"— privacy-guardian"
    )

    msg = _build_mime(
        from_display   = from_disp,
        to_addr        = to_addr,
        subject        = subject,
        body           = body,
        report_path    = report_path,
        checklist_path = checklist_path,
    )

    if method == "msmtp":
        _send_via_msmtp(msg, to_addr, msmtp_cfg)
    else:
        log.error(f"Unsupported email method: {method}")


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    parser = argparse.ArgumentParser(
        description="Send a privacy-guardian report on demand via msmtp"
    )
    parser.add_argument(
        "--profile", "-p", required=True,
        help="Profile ID (e.g. name1)"
    )
    parser.add_argument(
        "--report", "-r", required=True,
        help="Path to the HTML report file to send"
    )
    parser.add_argument(
        "--checklist", "-c", default=None,
        help="Optional: path to the manual checklist HTML file to attach"
    )
    args = parser.parse_args()

    send_report_on_demand(
        profile_id     = args.profile,
        report_path    = Path(args.report),
        checklist_path = Path(args.checklist) if args.checklist else None,
    )
