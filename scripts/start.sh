#!/usr/bin/env bash
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
V="$R/backend/.venv"
X="$R/backend/.run"
P="${BACKEND_PORT:-8787}"
PID="$X/backend.pid"
mkdir -p "$X"
if [ -f "$PID" ]; then
  p="$(cat "$PID")"
  if [ -d "/proc/$p" ]; then
    echo "  already running pid $p"
    exit 0
  fi
  rm -f "$PID"
fi
EVIDENCE_ROOT="${EVIDENCE_ROOT:-$HOME/jev-evidence}" \
  nohup "$V/bin/uvicorn" app:app --host 0.0.0.0 --port "$P" --app-dir "$R/backend" \
  > "$X/backend.log" 2>&1 &
echo $! > "$PID"
echo "  pid $(cat "$PID"); waiting for /health (max 20s)..."
UP=0
for i in $(seq 1 20); do
  sleep 1
  if [ ! -d "/proc/$(cat "$PID")" ]; then
    echo "  process exited before ready; log tail:"
    tail -n 30 "$X/backend.log"
    exit 0
  fi
  BODY="$(curl -sS --max-time 2 "http://localhost:$P/health" 2>&1)"
  if printf '%s' "$BODY" | grep -q 'jev_url'; then
    UP=1
    echo "  ready after ${i}s"
    break
  fi
done
if [ "$UP" -eq 0 ]; then
  echo "  not ready after 20s; log tail:"
  tail -n 30 "$X/backend.log"
fi
