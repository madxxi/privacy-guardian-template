#!/usr/bin/env bash
# =============================================================================
# privacy-guardian — setup.sh
# One-time environment setup. Run once after cloning.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[setup.sh] Creating virtual environment..."
python3 -m venv "${SCRIPT_DIR}/.venv"

echo "[setup.sh] Installing dependencies..."
source "${SCRIPT_DIR}/.venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r "${SCRIPT_DIR}/requirements.txt"

echo ""
echo "[setup.sh] ✅ Setup complete."
echo ""
echo "Next steps:"
echo "  1. Edit config/profiles.yaml — fill in your PII fields"
echo "  2. Test: bash scan.sh --verbose"
echo "  3. Schedule weekly: bash schedule.sh install"
echo ""
echo "⚠️  IMPORTANT: config/profiles.yaml is in .gitignore."
echo "   Never commit it to a public repo."
