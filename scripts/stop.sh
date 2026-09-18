#!/usr/bin/env bash
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID="$R/backend/.run/backend.pid"
if [ ! -f "$PID" ]; then
  echo "no pidfile"
  exit 0
fi
p="$(cat "$PID")"
if [ -d "/proc/$p" ]; then
  kill -TERM "$p"
  echo "SIGTERM $p"
else
  echo "not running"
fi
rm -f "$PID"
