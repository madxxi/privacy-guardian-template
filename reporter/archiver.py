"""
archiver.py
Report and log lifecycle management:
  - Move reports/checklists older than ARCHIVE_AFTER_DAYS into outputs/archive/
  - gzip files in the archive older than COMPRESS_AFTER_DAYS
  - Delete archived files older than DELETE_AFTER_DAYS
  - Rotate log files: compress after COMPRESS_AFTER_DAYS, delete after DELETE_AFTER_DAYS
Run automatically at the end of each scan, or manually via CLI.
"""
from __future__ import annotations

import gzip
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

ROOT          = Path(__file__).parent.parent
REPORTS_DIR   = ROOT / "outputs" / "reports"
ARCHIVE_DIR   = ROOT / "outputs" / "archive"
OPTOUT_DIR    = ROOT / "outputs" / "optout_queue"
LOG_DIR       = ROOT / "logs"

ARCHIVE_AFTER_DAYS  = 7     # move reports to archive/ after this many days
COMPRESS_AFTER_DAYS = 30    # gzip archived files after this many days
DELETE_AFTER_DAYS   = 120   # delete archived files after this many days

REPORT_GLOB     = ("report_*.html", "manual_checklist_*.html")
LOG_GLOB        = "scan_*.log"


def _file_age_days(path: Path) -> float:
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return (datetime.now() - mtime).total_seconds() / 86400


def _gzip_file(src: Path) -> Path:
    """Compress src to src.gz, remove original. Returns .gz path."""
    dst = src.with_suffix(src.suffix + ".gz")
    with open(src, "rb") as f_in, gzip.open(dst, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    src.unlink()
    log.debug(f"Compressed: {src.name} → {dst.name}")
    return dst


def run_archive() -> dict[str, int]:
    """
    Run full archive cycle. Returns counts of actions taken.
    """
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    counts = {"archived": 0, "compressed": 0, "deleted": 0, "logs_compressed": 0, "logs_deleted": 0}

    # ── Reports: archive → compress → delete ──────────────────────────────
    for glob in REPORT_GLOB:
        for f in REPORTS_DIR.glob(glob):
            age = _file_age_days(f)
            if age >= ARCHIVE_AFTER_DAYS:
                dest = ARCHIVE_DIR / f.name
                shutil.move(str(f), str(dest))
                log.info(f"Archived: {f.name} ({age:.0f} days old)")
                counts["archived"] += 1

    for f in ARCHIVE_DIR.glob("*.html"):
        age = _file_age_days(f)
        if age >= DELETE_AFTER_DAYS:
            f.unlink()
            log.info(f"Deleted (expired): {f.name} ({age:.0f} days old)")
            counts["deleted"] += 1
        elif age >= COMPRESS_AFTER_DAYS:
            _gzip_file(f)
            counts["compressed"] += 1

    for f in ARCHIVE_DIR.glob("*.html.gz"):
        age = _file_age_days(f)
        if age >= DELETE_AFTER_DAYS:
            f.unlink()
            log.info(f"Deleted (expired gz): {f.name} ({age:.0f} days old)")
            counts["deleted"] += 1

    # ── Opt-out queue dirs: archive after ARCHIVE_AFTER_DAYS ─────────────
    for scan_dir in OPTOUT_DIR.glob("scan_*"):
        if scan_dir.is_dir():
            age = _file_age_days(scan_dir)
            if age >= ARCHIVE_AFTER_DAYS:
                dest = ARCHIVE_DIR / scan_dir.name
                if not dest.exists():
                    shutil.move(str(scan_dir), str(dest))
                    log.info(f"Archived queue dir: {scan_dir.name}")
                    counts["archived"] += 1

    # ── Logs: compress after COMPRESS_AFTER_DAYS, delete after DELETE_AFTER_DAYS ─
    for f in LOG_DIR.glob(LOG_GLOB):
        age = _file_age_days(f)
        if age >= DELETE_AFTER_DAYS:
            f.unlink()
            log.info(f"Deleted log (expired): {f.name} ({age:.0f} days old)")
            counts["logs_deleted"] += 1
        elif age >= COMPRESS_AFTER_DAYS:
            _gzip_file(f)
            counts["logs_compressed"] += 1

    for f in LOG_DIR.glob("*.log.gz"):
        age = _file_age_days(f)
        if age >= DELETE_AFTER_DAYS:
            f.unlink()
            log.info(f"Deleted log gz (expired): {f.name} ({age:.0f} days old)")
            counts["logs_deleted"] += 1

    log.info(
        f"Archive cycle complete — "
        f"archived={counts['archived']}, "
        f"compressed={counts['compressed']}, "
        f"deleted={counts['deleted']}, "
        f"logs_compressed={counts['logs_compressed']}, "
        f"logs_deleted={counts['logs_deleted']}"
    )
    return counts


def report_status() -> None:
    """Print a summary of current report/archive file ages to stdout."""
    print(f"\n{'─'*60}")
    print(f"{'FILE':<45} {'AGE':>6}  STATUS")
    print(f"{'─'*60}")

    def _print_dir(directory: Path, glob: str, label: str) -> None:
        files = sorted(directory.glob(glob), key=lambda f: f.stat().st_mtime, reverse=True)
        for f in files:
            age  = _file_age_days(f)
            if age >= DELETE_AFTER_DAYS:
                status = "🔴 DELETE (next run)"
            elif age >= COMPRESS_AFTER_DAYS:
                status = "🟡 COMPRESS (next run)"
            elif age >= ARCHIVE_AFTER_DAYS:
                status = "📦 ARCHIVE (next run)"
            else:
                status = "✅ current"
            print(f"  {f.name:<43} {age:>5.0f}d  {status}")

    print("REPORTS (active):")
    for glob in REPORT_GLOB:
        _print_dir(REPORTS_DIR, glob, "reports")

    print("\nARCHIVE:")
    _print_dir(ARCHIVE_DIR, "*.html",    "archive")
    _print_dir(ARCHIVE_DIR, "*.html.gz", "archive")

    print("\nLOGS:")
    _print_dir(LOG_DIR, "*.log",    "logs")
    _print_dir(LOG_DIR, "*.log.gz", "logs")

    thresholds = (
        f"\nThresholds: archive after {ARCHIVE_AFTER_DAYS}d | "
        f"compress after {COMPRESS_AFTER_DAYS}d | "
        f"delete after {DELETE_AFTER_DAYS}d"
    )
    print(thresholds)
    print(f"{'─'*60}\n")


# ── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])

    parser = argparse.ArgumentParser(description="privacy-guardian archive manager")
    parser.add_argument("--run",    action="store_true", help="Run archive cycle now")
    parser.add_argument("--status", action="store_true", help="Show file age status")
    args = parser.parse_args()

    if args.status:
        report_status()
    elif args.run:
        run_archive()
    else:
        parser.print_help()
