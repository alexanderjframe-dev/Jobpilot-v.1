#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
. .venv/bin/activate
if [ ! -f .venv/.jobpilot-installed ]; then
  python -m pip install -r requirements.txt
  touch .venv/.jobpilot-installed
fi
printf '\nJobPilot is starting. Open http://127.0.0.1:8765 in your browser.\nStop it with Ctrl+C when finished.\n\n'
python -m uvicorn app:app --host 127.0.0.1 --port 8765
