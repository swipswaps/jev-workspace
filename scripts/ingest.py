#!/usr/bin/env python3
"""Deterministic chat-log ingestion via the backend API."""
import hashlib
import json
import sys
from pathlib import Path

import httpx

BACKEND = "http://localhost:8787"


def main():
    if len(sys.argv) < 3:
        print("usage: ingest.py <file.txt> <conversation_id>")
        return 0
    path = Path(sys.argv[1])
    cid = sys.argv[2]
    if not path.is_file():
        print("not found: " + str(path))
        return 0
    raw = path.read_bytes()
    print("file: " + str(path))
    print("sha256: " + hashlib.sha256(raw).hexdigest())
    print("bytes: " + str(len(raw)))
    with httpx.Client(timeout=30.0) as c:
        r = c.post(BACKEND + "/ingest",
                   files={"file": (path.name, raw, "text/plain")},
                   data={"source": "cli"})
        if r.status_code != 200:
            print("ingest failed: " + str(r.status_code))
            print(r.text[:300])
            return 0
        print(json.dumps(r.json(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
