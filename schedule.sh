#!/usr/bin/env bash
# =============================================================================
# privacy-guardian — schedule.sh
# Installs or removes the weekly cron job.
# Default: Sundays at 8:00 AM (runs after job scouts)
#
# Usage:
#   bash schedule.sh install       # install cron (default: Sun 8:00 AM)
#   bash schedule.sh install 0 9   # custom: Sun 9:00 AM (day hour)
#   bash schedule.sh remove        # remove cron
#   bash schedule.sh status        # show current cron entry
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAN_CMD="${SCRIPT_DIR}/scan.sh"
CRON_TAG="privacy-guardian"

# Default schedule: 8:00 AM every Sunday (0 = Sunday)
DEFAULT_HOUR=8
DEFAULT_DOW=0   # 0 = Sunday

usage() {
  echo "Usage: bash schedule.sh [install|remove|status] [day_of_week hour]"
  exit 1
}

cmd="${1:-status}"

case "$cmd" in

  install)
    DOW="${2:-$DEFAULT_DOW}"
    HOUR="${3:-$DEFAULT_HOUR}"
    CRON_LINE="0 ${HOUR} * * ${DOW} bash ${SCAN_CMD} >> ${SCRIPT_DIR}/logs/cron.log 2>&1  # ${CRON_TAG}"

    # Remove existing entry first
    crontab -l 2>/dev/null | grep -v "$CRON_TAG" | crontab - 2>/dev/null || true

    # Install new entry
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -

    echo "[schedule.sh] Cron installed:"
    echo "  $CRON_LINE"
    echo ""
    echo "  Day-of-week legend: 0=Sun 1=Mon 2=Tue 3=Wed 4=Thu 5=Fri 6=Sat"
    ;;

  remove)
    crontab -l 2>/dev/null | grep -v "$CRON_TAG" | crontab -
    echo "[schedule.sh] Cron entry removed."
    ;;

  status)
    echo "[schedule.sh] Current privacy-guardian cron entries:"
    crontab -l 2>/dev/null | grep "$CRON_TAG" || echo "  (none installed)"
    ;;

  *)
    usage
    ;;
esac
