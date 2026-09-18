#!/usr/bin/env bash
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
V="$R/backend/.venv"
X="$R/backend/.run"
P="${BACKEND_PORT:-8765}"
PID="$X/backend.pid"
mkdir -p "$X"
if [ ! -d "$V" ]; then
  python3 -m venv "$V"
fi
"$V/bin/pip" install --quiet --upgrade pip
"$V/bin/pip" install --quiet -r "$R/backend/requirements.txt"
if [ -f "$PID" ]; then
  p="$(cat "$PID")"
  if [ -d "/proc/$p" ]; then
    echo "already running pid $p"
    exit 0
  fi
  rm -f "$PID"
fi
EVIDENCE_ROOT="${EVIDENCE_ROOT:-$HOME/jev-evidence}" \
  nohup "$V/bin/uvicorn" app:app --host 0.0.0.0 --port "$P" --app-dir "$R/backend" \
  > "$X/backend.log" 2>&1 &
echo $! > "$PID"
echo "started on :$P pid $(cat "$PID")"
