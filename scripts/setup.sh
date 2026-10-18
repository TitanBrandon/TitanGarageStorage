#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
TITAN_ENV_DIR="${TITAN_VENV:-$PWD/.venv}"
TITAN_SETUP_PYTHON="${TITAN_PYTHON:-python3}"
"$TITAN_SETUP_PYTHON" -c 'import sys; assert sys.version_info[:2] == (3,12), "Use Python 3.12 for the pinned environment"'
if [[ ! -x "$TITAN_ENV_DIR/bin/python" ]]; then
  "$TITAN_SETUP_PYTHON" -m venv "$TITAN_ENV_DIR"
fi
"$TITAN_ENV_DIR/bin/python" -m pip install --disable-pip-version-check -r backend/requirements-hosted.txt
case "${1:-}" in
  "") ;;
  --worker)
    "$TITAN_ENV_DIR/bin/python" -m pip install --disable-pip-version-check -r backend/requirements-worker.txt
    "$TITAN_ENV_DIR/bin/python" -m backend.download_model
    if ! command -v "${BLENDER_BIN:-blender}" >/dev/null 2>&1; then
      printf 'Install Blender before starting the worker, or use Dockerfile.worker. See DEPLOY.md.\n' >&2
      exit 1
    fi
    ;;
  *) printf 'Usage: bash scripts/setup.sh [--worker]\n' >&2; exit 2 ;;
esac
npm ci --no-fund --no-audit
npm run build
printf '\nWebsite setup complete. Configure SITE_PASSWORD, WORKER_URL and WORKER_TOKEN, then run npm run dev.\n'
printf 'A worker is a separate process with Blender, the verified depth model and durable storage. See DEPLOY.md.\n'
