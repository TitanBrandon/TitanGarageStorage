#!/bin/bash
cd "$(dirname "$0")"
if command -v python3.12 >/dev/null 2>&1; then
  python3.12 scripts/run_local.py
else
  python3 scripts/run_local.py
fi
read -r -p "Press Return to close this window. "
