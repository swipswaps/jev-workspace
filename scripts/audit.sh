#!/usr/bin/env bash
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TS="$(date +%Y%m%dT%H%M%S)"
OUT="$R/evidence/derived/$TS"
mkdir -p "$OUT"
REPORT="$OUT/REPORT.txt"
{
  echo "JEV WORKSPACE AUDIT - $TS"
  echo "========================================"
  echo ""
  echo "[git status]"
  git -C "$R" status --short 2>&1 | head -n 40
  echo ""
  echo "[last commit]"
  git -C "$R" log -1 --oneline 2>&1
  echo ""
  echo "[backend health]"
  curl -sS -o "$OUT/health.json" -w "http_code=%{http_code}\n" "http://localhost:8787/health" 2>&1
  if [ -f "$OUT/health.json" ]; then
    echo "body:"
    head -c 400 "$OUT/health.json"
    echo ""
  fi
  echo ""
  echo "[conversations]"
  curl -sS -o "$OUT/convs.json" -w "http_code=%{http_code}\n" "http://localhost:8787/conversations" 2>&1
  echo ""
  echo "[jev calls]"
  curl -sS -o "$OUT/jevcalls.json" -w "http_code=%{http_code}\n" "http://localhost:8787/jev/calls" 2>&1
  echo ""
  echo "[python syntax]"
  python3 -m py_compile "$R/backend/app.py" 2>&1 && echo "  backend/app.py: ok"
} > "$REPORT" 2>&1
ln -sfn "$OUT" "$R/evidence/derived/latest"
echo "audit written: $REPORT"
cat "$REPORT"
