#!/usr/bin/env bash
# =============================================================================
# privacy-guardian — scan.sh
# Main entry point for all operations.
#
# SCAN (manual):
#   bash scan.sh                              # all profiles
#   bash scan.sh --profiles name1              # one profile
#   bash scan.sh --profiles name1,name2       # comma-separated
#   bash scan.sh --profiles name1 name2       # space-separated
#   bash scan.sh --profiles name1 --verbose    # with debug output
#   bash scan.sh --no-email --no-archive      # skip email and archiving
#
# SCAN (called by Windows Task Scheduler — do not use manually):
#   bash scan.sh --scheduled
#
# SCHEDULE — manage Windows Task Scheduler from WSL (no PowerShell path hassle):
#   bash scan.sh schedule install
#   bash scan.sh schedule install -Profiles "name1,name2"
#   bash scan.sh schedule status
#   bash scan.sh schedule remove
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${SCRIPT_DIR}/.venv"
LOG_DIR="${SCRIPT_DIR}/logs"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$LOG_DIR"

# ── Schedule subcommand — invoke schedule.ps1 via powershell.exe from WSL ─────
if [[ "${1:-}" == "schedule" ]]; then
  shift
  PS1_WIN="$(wslpath -w "${SCRIPT_DIR}/schedule.ps1")"
  echo "[scan.sh] Running: powershell.exe -ExecutionPolicy Bypass -File \"${PS1_WIN}\" $*"
  powershell.exe -ExecutionPolicy Bypass -File "${PS1_WIN}" "$@"
  exit 0
fi

# ── Activate venv ─────────────────────────────────────────────────────────────
if [ ! -d "$VENV" ]; then
  echo "[scan.sh] ERROR: Virtual environment not found at $VENV"
  echo "[scan.sh] Run: bash setup.sh"
  exit 1
fi

source "${VENV}/bin/activate"

# ── Run — pass all arguments straight through to main.py ──────────────────────
echo "[scan.sh] Starting privacy-guardian scan at $TIMESTAMP"

python3 "${SCRIPT_DIR}/scanner/main.py" "$@"

echo "[scan.sh] Scan complete."
