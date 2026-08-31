#!/usr/bin/env python3
"""
privacy-guardian — main.py
Orchestrator. Each profile gets its own isolated report, checklist, and email.
No cross-profile data in any generated file.

Profile selection:
  --profiles name1 name2          space-separated
  --profiles name1,name2          comma-separated
  --profiles all  (or omit)       run all profiles
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))
from scanner.broker_scanner import BrokerScanner
from scanner.public_records import PublicRecordsScanner
from reporter.report_builder import ReportBuilder
from reporter.manual_checklist import ManualChecklistBuilder
from reporter.notifier import send_reports
from reporter.archiver import run_archive
from reporter.tracker import ScanTracker

ROOT       = Path(__file__).parent.parent
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "outputs"
LOG_DIR    = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_DIR / f"scan_{datetime.now():%Y%m%d}.log"),
        ],
    )


def load_yaml(filename: str) -> dict:
    with open(CONFIG_DIR / filename) as f:
        return yaml.safe_load(f)


def _resolve_profile_ids(raw: list[str] | None, all_profiles: list[dict]) -> list[str]:
    """
    Accept space-separated or comma-separated IDs, or 'all'/None for everyone.
    Returns a validated list of profile IDs.
    """
    all_ids = [p["id"] for p in all_profiles]

    if not raw:
        return all_ids

    requested: list[str] = []
    for token in raw:
        for part in token.split(","):
            part = part.strip()
            if part:
                requested.append(part)

    if requested == ["all"]:
        return all_ids

    invalid = [r for r in requested if r not in all_ids]
    if invalid:
        print(
            f"ERROR: Unknown profile ID(s): {invalid}\n"
            f"Available: {all_ids}",
            file=sys.stderr,
        )
        sys.exit(1)

    return requested


def run_scan(
    profile_ids: list[str] | None = None,
    verbose:     bool = False,
    no_email:    bool = False,
    no_archive:  bool = False,
    scheduled:   bool = False,
) -> None:
    setup_logging(verbose)
    log = logging.getLogger(__name__)

    log.info("=" * 60)
    log.info("privacy-guardian scan started")
    log.info(f"Timestamp : {datetime.now():%Y-%m-%d %H:%M:%S}")
    log.info(f"Triggered : {'scheduled' if scheduled else 'manual'}")
    log.info("=" * 60)

    profiles_cfg = load_yaml("profiles.yaml")
    brokers_cfg  = load_yaml("brokers.yaml")
    all_profiles = profiles_cfg["profiles"]
    brokers      = brokers_cfg["brokers"]

    selected_ids = _resolve_profile_ids(profile_ids, all_profiles)
    profiles     = [p for p in all_profiles if p["id"] in selected_ids]
    log.info(f"Profiles  : {selected_ids}")

    tracker     = ScanTracker(OUTPUT_DIR / "scan_history.db")
    all_results = []

    for profile in profiles:
        display = profile.get("display_name", profile["id"])
        log.info(f"\n── Profile: {profile['id']} ({display}) ──")

        broker_results = BrokerScanner(profile, brokers, verbose=verbose).scan_all()
        pub_results    = PublicRecordsScanner(profile, brokers, verbose=verbose).scan_all()

        profile_results = {
            "profile":        profile,
            "broker_results": broker_results,
            "pub_results":    pub_results,
            "scan_time":      datetime.now().isoformat(),
        }
        all_results.append(profile_results)
        tracker.record(profile_results)

    reports_dir = OUTPUT_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # ── One report per profile ─────────────────────────────────────────────
    report_paths = ReportBuilder(reports_dir).build(all_results)
    for pid, path in report_paths.items():
        log.info(f"✅ Report [{pid}]:     {path.name}")

    # ── One checklist per profile (only if blocked items exist) ───────────
    checklist_paths = ManualChecklistBuilder(reports_dir, db_path=OUTPUT_DIR / "scan_history.db").build(all_results)
    for pid, path in checklist_paths.items():
        log.info(f"✅ Checklist [{pid}]: {path.name}")
    if not checklist_paths:
        log.info("✅ Manual checklists: nothing blocked — skipped")

    # ── One opt-out text queue per profile ────────────────────────────────
    queue_dir = OUTPUT_DIR / "optout_queue" / f"scan_{datetime.now():%Y%m%d}"
    queue_dir.mkdir(parents=True, exist_ok=True)
    ReportBuilder(reports_dir).write_optout_queue(all_results, queue_dir)
    log.info(f"✅ Opt-out queues:    {queue_dir}")

    # ── Email: each profile receives only its own report ──────────────────
    if not no_email:
        log.info("\nSending email notifications...")
        send_reports(
            all_results     = all_results,
            report_paths    = report_paths,
            checklist_paths = checklist_paths,
            scheduled       = scheduled,
        )
    else:
        log.info("Email notifications skipped (--no-email)")

    # ── Archive maintenance ────────────────────────────────────────────────
    if not no_archive:
        log.info("\nRunning archive maintenance...")
        run_archive()
    else:
        log.info("Archive maintenance skipped (--no-archive)")

    log.info("\nprivacy-guardian scan complete.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="privacy-guardian scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Profile selection examples:
  bash scan.sh                          # all profiles
  bash scan.sh --profiles all           # all profiles (explicit)
  bash scan.sh --profiles name1          # one profile
  bash scan.sh --profiles name1 name2   # space-separated
  bash scan.sh --profiles name1,name2   # comma-separated
  bash scan.sh -p name1 -p name2        # repeated flag

On-demand email send (no rescan):
  python3 -m reporter.notifier --profile name1 \\
      --report outputs/reports/report_name1_20260830_003134.html
        """,
    )
    parser.add_argument(
        "--profiles", "-p",
        nargs="+",
        metavar="ID",
        help="Profile ID(s) to scan. Comma or space separated. Omit for all.",
    )
    parser.add_argument("--verbose",    "-v", action="store_true",
                        help="Enable debug logging")
    parser.add_argument("--no-email",   action="store_true",
                        help="Skip email notifications for this run")
    parser.add_argument("--no-archive", action="store_true",
                        help="Skip archive maintenance for this run")
    parser.add_argument("--scheduled",  action="store_true",
                        help="Mark this as a scheduled run (affects email_on_scheduled_run setting)")
    args = parser.parse_args()

    run_scan(
        profile_ids = args.profiles,
        verbose     = args.verbose,
        no_email    = args.no_email,
        no_archive  = args.no_archive,
        scheduled   = args.scheduled,
    )


if __name__ == "__main__":
    main()
