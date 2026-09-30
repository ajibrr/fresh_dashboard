#!/usr/bin/env bash
# Launcher for Mac / Linux / VPS.
#
# Usage:
#   ./run.sh                          # defaults below
#   ./run.sh <mode> <config>
#   ./run.sh optimize configs/optimization.json
set -e

# ============================================================
# Change this only if the data/results should live somewhere
# OTHER than the folder this script is in. Leave empty to
# auto-detect (correct on any machine, including a fresh VPS).
# ============================================================
PROJECT_ROOT=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -n "$PROJECT_ROOT" ]; then
    export NIFTY_PROJECT_ROOT="$PROJECT_ROOT"
fi

if [ ! -d venv ]; then
    echo "No venv found - creating one..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

MODE="${1:-optimize}"
CONFIG="${2:-configs/optimization.json}"

echo "Running: python main.py --mode $MODE --config $CONFIG"
python main.py --mode "$MODE" --config "$CONFIG"
