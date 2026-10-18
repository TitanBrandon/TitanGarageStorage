#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
TITAN_ENV_DIR="${TITAN_VENV:-$PWD/.venv}"
python3 -m venv "$TITAN_ENV_DIR"
"$TITAN_ENV_DIR/bin/python" -m pip install -r backend/requirements.txt
"$TITAN_ENV_DIR/bin/python" -m backend.download_model
npm ci --no-fund --no-audit
npm run build
printf '\nSetup complete. Run npm run dev (set TITAN_PYTHON if using a custom venv).\n'
