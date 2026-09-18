"""Jev Workspace backend.

FastAPI on 8787. Deterministic chat-log ingestion, Jev structured
judgments (noul / choice / score), SQLite + FTS5 evidence search, and
audit-run management. Jev is the judgment layer. SQLite is the
evidence layer. The backend returns typed decisions, not prose.
"""
import hashlib
import json
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from starlette.datastructures import MutableHeaders

EVIDENCE_ROOT = Path(os.environ.get("EVIDENCE_ROOT", str(Path.home() / "jev-evidence")))
DB_PATH = EVIDENCE_ROOT / "index" / "jev.db"
JEV_URL = os.environ.get("TYPESAFE_BASE_URL", "https://api.typesafe.ai")
JEV_PATH = os.environ.get("TYPESAFE_PATH", "/ask")
JEV_KEY = os.environ.get("TYPESAFE_API_KEY", "")
JEV_MODEL = os.environ.get("JEV_MODEL", "jev-latest")
PARSER_VERSION = "2.0.0"


def db():
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_ROOT / "index").mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def fts_available(con):
    opts = [r[0] for r in con.execute("pragma compile_options").fetchall()]
    return any("FTS5" in o for o in opts)


def init_db():
    con = db()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            source TEXT,
            capture_file TEXT,
            sha256 TEXT,
            bytes INTEGER,
            captured_at TEXT,
            parser_version TEXT
        );
        CREATE TABLE IF NOT EXISTS turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT,
            turn_number INTEGER,
            speaker TEXT,
            text TEXT,
            code_blocks TEXT,
            paths TEXT,
            commands TEXT,
            errors TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS jev_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT,
            ns TEXT,
            instructions TEXT,
            result TEXT,
            latency_ms INTEGER,
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_turns_conv ON turns(conversation_id, turn_number);
        CREATE INDEX IF NOT EXISTS idx_jev_conv ON jev_calls(conversation_id);
    """)
    if fts_available(con):
        con.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(
                text, code_blocks, paths, commands, errors,
                content='turns', content_rowid='id'
            );
            CREATE TRIGGER IF NOT EXISTS turns_ai AFTER INSERT ON turns BEGIN
                INSERT INTO turns_fts(rowid, text, code_blocks, paths, commands, errors)
                VALUES (new.id, new.text, new.code_blocks, new.paths, new.commands, new.errors);
            END;
            CREATE TRIGGER IF NOT EXISTS turns_ad AFTER DELETE ON turns BEGIN
                INSERT INTO turns_fts(turns_fts, rowid, text, code_blocks, paths, commands, errors)
                VALUES ('delete', old.id, old.text, old.code_blocks, old.paths, old.commands, old.errors);
            END;
        """)
        # backfill: index any turn rows that predate the trigger
        con.execute("""
            INSERT INTO turns_fts(rowid, text, code_blocks, paths, commands, errors)
            SELECT id, text, code_blocks, paths, commands, errors FROM turns
            WHERE id NOT IN (SELECT rowid FROM turns_fts)
        """)
        con.commit()
    con.commit()
    con.close()


# Multi-format turn detection. Each entry is (pattern, group_index).
# order matters: first match wins.
TURN_PATTERNS = [
    # ### user / ### assistant                              [18]
    (re.compile(r"^(#{1,6})\s+(user|assistant|human|ai|system|chatgpt)\s*$",
                re.MULTILINE | re.IGNORECASE), 2),
    # **user** / **assistant**
    (re.compile(r"^\*\*(user|assistant|human|ai|system|chatgpt)\*\*\s*$",
                re.MULTILINE | re.IGNORECASE), 1),
    # You said: / ChatGPT said:                             [10]
    (re.compile(r"^(you\s+said|chatgpt\s+said|assistant\s+said|user\s+said)\s*:?\s*$",
                re.MULTILINE | re.IGNORECASE), 1),
    # user: / assistant: (bare colon)                       [14]
    (re.compile(r"^(user|assistant|human|ai|system|chatgpt)\s*:\s*$",
                re.MULTILINE | re.IGNORECASE), 1),
]

CODE_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
PATH_RE = re.compile(r"(?:~|/)[\w./-]+\.\w+")
CMD_RE = re.compile(r"^\s*\$\s+(.+)$", re.MULTILINE)
ERR_RE = re.compile(r"(?:Error|error|ERROR|Traceback|FAILED|failed)[:\s].{0,200}")


def normalize_role(role):
    r = role.lower().strip().rstrip(":")
    if r in ("user", "human", "you said", "user said"):
        return "user"
    if r in ("assistant", "ai", "system", "chatgpt", "chatgpt said", "assistant said"):
        return "assistant"
    return "unknown"


def _turn_matches(raw):
    """Return (matches, group_index) for the first pattern that matches."""
    for pat, grp in TURN_PATTERNS:
        m = list(pat.finditer(raw))
        if m:
            return m, grp
    return [], 1


FRAGMENT_SPLIT_RE = re.compile(r"\n\s*\n+")


def parse_transcript(raw, conversation_id):
    matches, speaker_group = _turn_matches(raw)
    turns = []

    # Markerless fallback: file has no role headings at all. This is the
    # default output of ChatGPT's select-all + Ctrl+C on the web UI.
    # https://community.openai.com/t/how-to-copy-chatgpt-conversation-with-markdown-formatting/336646
    # We store each blank-line-separated block as a "fragment" so that
    # search and audit still work. Speaker remains "fragment" because we
    # cannot determine role without markers. Do not fabricate.
    if not matches:
        blocks = FRAGMENT_SPLIT_RE.split(raw)
        for i, blk in enumerate(blocks):
            blk = blk.strip()
            if not blk:
                continue
            turns.append({
                "conversation_id": conversation_id,
                "turn_number": i,
                "speaker": "fragment",
                "text": blk,
                "code_blocks": json.dumps([c.group(2) for c in CODE_RE.finditer(blk)]),
                "paths": json.dumps(sorted(set(PATH_RE.findall(blk)))),
                "commands": json.dumps(CMD_RE.findall(blk)),
                "errors": json.dumps(ERR_RE.findall(blk)),
                "created_at": datetime.now().isoformat(),
            })
        return {"conversation_id": conversation_id,
                "turn_count": len(turns),
                "turns": turns,
                "mode": "fragment"}
    # pre-heading text is stored as turn 0 with unknown speaker
    if matches and matches[0].start() > 0:
        pre = raw[:matches[0].start()].strip()
        if pre:
            turns.append({
                "conversation_id": conversation_id,
                "turn_number": 0,
                "speaker": "unknown",
                "text": pre,
                "code_blocks": json.dumps([c.group(2) for c in CODE_RE.finditer(pre)]),
                "paths": json.dumps(sorted(set(PATH_RE.findall(pre)))),
                "commands": json.dumps(CMD_RE.findall(pre)),
                "errors": json.dumps(ERR_RE.findall(pre)),
                "created_at": datetime.now().isoformat(),
            })
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        body = raw[start:end].strip()
        speaker_raw = m.group(speaker_group)
        speaker = normalize_role(speaker_raw)
        code_blocks = [c.group(2) for c in CODE_RE.finditer(body)]
        paths = sorted(set(PATH_RE.findall(body)))
        commands = CMD_RE.findall(body)
        errors = ERR_RE.findall(body)
        turns.append({
            "conversation_id": conversation_id,
            "turn_number": i + 1,
            "speaker": speaker,
            "text": body,
            "code_blocks": json.dumps(code_blocks),
            "paths": json.dumps(paths),
            "commands": json.dumps(commands),
            "errors": json.dumps(errors),
            "created_at": datetime.now().isoformat(),
        })
    return {"conversation_id": conversation_id, "turn_count": len(turns), "turns": turns}


def store_transcript(parsed, source, capture_file, sha256, raw_bytes):
    con = db()
    con.execute(
        "INSERT OR REPLACE INTO conversations (id, source, capture_file, sha256, bytes, captured_at, parser_version) VALUES (?,?,?,?,?,?,?)",
        (parsed["conversation_id"], source, capture_file, sha256, raw_bytes,
         datetime.now().isoformat(), PARSER_VERSION))
    for t in parsed["turns"]:
        con.execute(
            "INSERT INTO turns (conversation_id, turn_number, speaker, text, code_blocks, paths, commands, errors, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (t["conversation_id"], t["turn_number"], t["speaker"], t["text"],
             t["code_blocks"], t["paths"], t["commands"], t["errors"], t["created_at"]))
    con.commit()
    con.close()


async def jev_call(ns, instructions, state, criteria):
    if os.environ.get("JEV_MOCK") == "1":
        import hashlib as _h
        seed = (ns + "|" + instructions + "|" + str(state)[:200]).encode()
        h = int(_h.sha256(seed).hexdigest()[:8], 16)
        if ns == "noul":
            p = (h % 1000) / 1000.0
            return {"noul": p, "confidence": abs(p - 0.5) * 2, "mock": True}
        if ns == "choice":
            keys = list(criteria.keys()) if isinstance(criteria, dict) and criteria else ["a", "b"]
            idx = h % len(keys)
            probs = {k: (1.0 if i == idx else 0.0) for i, k in enumerate(keys)}
            return {"choice": keys[idx], "probabilities": probs, "mock": True}
        if ns == "score":
            levels = criteria if isinstance(criteria, list) and criteria else ["low", "medium", "high"]
            idx = h % len(levels)
            probs = {str(k): (1.0 if i == idx else 0.0) for i, k in enumerate(levels)}
            return {"score": levels[idx], "probabilities": probs, "mock": True}
        return {"mock": True, "ns": ns, "seed": h}
    if not JEV_KEY:
        raise HTTPException(503, "TYPESAFE_API_KEY not set")
    payload = {
        "model": JEV_MODEL,
        "ns": ns,
        "instructions": instructions,
        "state": state,
        "criteria": criteria,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            JEV_URL + JEV_PATH,
            headers={"Authorization": "Bearer " + JEV_KEY,
                     "Content-Type": "application/json"},
            json=payload,
        )
        if r.status_code != 200:
            raise HTTPException(r.status_code, "jev error: " + r.text[:300])
        return r.json()


app = FastAPI(title="Jev Workspace", version="2.0.0")


class PrivateNetworkAccessMiddleware:
    """Adds Access-Control-Allow-Private-Network: true to every response.

    Starlette added allow_private_network natively in 0.51.0 (Jan 2026).
    FastAPI 0.115.0 pins starlette<0.42.0, so this shim is required.
    It does NOT short-circuit the CORS preflight: CORS runs first and
    produces its response, then this middleware adds the PNA header.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Access-Control-Allow-Private-Network"] = "true"
            await send(message)

        await self.app(scope, receive, send_wrapper)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(PrivateNetworkAccessMiddleware)

init_db()


@app.get("/health")
def health():
    ok, err = False, ""
    try:
        con = db()
        con.execute("SELECT 1").fetchone()
        con.close()
        ok = True
    except Exception as e:
        err = str(e)
    return {
        "status": "ok",
        "db": ok,
        "db_error": err,
        "jev_configured": bool(JEV_KEY),
        "jev_mock": os.environ.get("JEV_MOCK") == "1",
        "jev_url": JEV_URL + JEV_PATH,
        "hostname": os.uname().nodename,
        "time": datetime.now().isoformat(),
    }


@app.post("/ingest")
async def ingest(file: UploadFile = File(...), source: str = Form("chatgpt")):
    raw = await file.read()
    sha = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8", "replace")
    cid = Path(file.filename or "unknown").stem
    parsed = parse_transcript(text, cid)
    store_transcript(parsed, source, file.filename or "", sha, len(raw))
    (EVIDENCE_ROOT / "raw").mkdir(parents=True, exist_ok=True)
    (EVIDENCE_ROOT / "raw" / (cid + ".txt")).write_bytes(raw)
    (EVIDENCE_ROOT / "normalized").mkdir(parents=True, exist_ok=True)
    with (EVIDENCE_ROOT / "normalized" / (cid + ".jsonl")).open("w") as f:
        for t in parsed["turns"]:
            f.write(json.dumps(t) + "\n")
    return {"conversation_id": cid, "sha256": sha, "bytes": len(raw),
            "turn_count": parsed["turn_count"]}


@app.get("/conversations")
def conversations():
    con = db()
    rows = [dict(r) for r in con.execute(
        "SELECT id, source, bytes, captured_at, parser_version FROM conversations ORDER BY captured_at DESC"
    ).fetchall()]
    con.close()
    return {"conversations": rows, "count": len(rows)}


@app.get("/turns/{conversation_id}")
def turns(conversation_id: str, limit: int = 200):
    con = db()
    # exact match first; if none, try prefix match (handles _0001 suffix)
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM turns WHERE conversation_id=? ORDER BY turn_number LIMIT ?",
        (conversation_id, limit)).fetchall()]
    if not rows:
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM turns WHERE conversation_id LIKE ? ORDER BY turn_number LIMIT ?",
            (conversation_id + "%", limit)).fetchall()]
    con.close()
    return {"turns": rows, "count": len(rows)}


@app.get("/debug/raw/{conversation_id}")
def debug_raw(conversation_id: str, lines: int = 40):
    """Show the first N lines of the raw transcript for parser diagnosis."""
    raw_dir = EVIDENCE_ROOT / "raw"
    if not raw_dir.is_dir():
        raise HTTPException(404, "no raw evidence directory")
    candidates = list(raw_dir.glob(conversation_id + "*"))
    if not candidates:
        raise HTTPException(404, "no matching raw file")
    text = candidates[0].read_text(errors="replace")
    head = text.splitlines()[:lines]
    # count which turn patterns match, to identify the format
    counts = {}
    for i, (pat, _) in enumerate(TURN_PATTERNS):
        counts["pattern_" + str(i)] = len(pat.findall(text))
    return {"file": str(candidates[0]), "lines": head,
            "match_counts": counts, "total_bytes": len(text)}


@app.get("/search")
def search(q: str, limit: int = 50):
    con = db()
    try:
        if fts_available(con):
            rows = [dict(r) for r in con.execute(
                "SELECT t.* FROM turns_fts f JOIN turns t ON t.id=f.rowid "
                "WHERE turns_fts MATCH ? LIMIT ?", (q, limit)).fetchall()]
        else:
            like = "%" + q + "%"
            rows = [dict(r) for r in con.execute(
                "SELECT * FROM turns WHERE text LIKE ? OR code_blocks LIKE ? "
                "OR paths LIKE ? LIMIT ?", (like, like, like, limit)).fetchall()]
    except sqlite3.OperationalError as e:
        con.close()
        raise HTTPException(400, "search failed: " + str(e))
    con.close()
    return {"results": rows, "count": len(rows)}


@app.post("/jev/judge")
async def jev_judge(payload: dict):
    ns = payload.get("ns")
    instructions = payload.get("instructions", "")
    state = payload.get("state", "")
    criteria = payload.get("criteria", {})
    cid = payload.get("conversation_id", "")
    if ns not in ("noul", "choice", "score"):
        raise HTTPException(400, "ns must be noul, choice, or score")
    if not instructions or not state:
        raise HTTPException(400, "instructions and state are required")
    t0 = time.time()
    result = await jev_call(ns, instructions, state, criteria)
    latency = int((time.time() - t0) * 1000)
    con = db()
    con.execute(
        "INSERT INTO jev_calls (conversation_id, ns, instructions, result, latency_ms, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (cid, ns, instructions, json.dumps(result), latency,
         datetime.now().isoformat()))
    con.commit()
    con.close()
    return {"result": result, "latency_ms": latency}


@app.get("/jev/calls")
def jev_calls(limit: int = 50):
    con = db()
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM jev_calls ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
    con.close()
    return {"calls": rows, "count": len(rows)}


@app.get("/debug/formats/{conversation_id}")
def debug_formats(conversation_id: str):
    """Report which turn patterns match the raw file, plus a sample of
    the first non-empty line. Used to identify the export format."""
    raw_dir = EVIDENCE_ROOT / "raw"
    if not raw_dir.is_dir():
        raise HTTPException(404, "no raw dir")
    candidates = list(raw_dir.glob(conversation_id + "*"))
    if not candidates:
        raise HTTPException(404, "no matching raw file")
    text = candidates[0].read_text(errors="replace")
    counts = {}
    for i, (pat, _) in enumerate(TURN_PATTERNS):
        counts["pattern_" + str(i)] = len(pat.findall(text))
    frag_count = len(FRAGMENT_SPLIT_RE.split(text))
    nonempty = [ln for ln in text.splitlines() if ln.strip()][:5]
    return {"file": str(candidates[0]), "match_counts": counts,
            "fragment_count": frag_count, "first_lines": nonempty,
            "total_bytes": len(text)}


@app.get("/audit/runs")
def audit_runs():
    root = EVIDENCE_ROOT / "derived"
    if not root.is_dir():
        return {"runs": [], "root": str(root)}
    out = []
    for d in sorted(root.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        r = d / "REPORT.txt"
        out.append({"name": d.name, "has_report": r.is_file(),
                    "size": r.stat().st_size if r.is_file() else 0})
    return {"runs": out, "root": str(root)}


@app.get("/audit/latest", response_class=PlainTextResponse)
def audit_latest():
    root = EVIDENCE_ROOT / "derived"
    if not root.is_dir():
        raise HTTPException(404, "no audit runs")
    runs = sorted([d for d in root.iterdir() if d.is_dir()], reverse=True)
    if not runs:
        raise HTTPException(404, "no audit runs")
    r = runs[0] / "REPORT.txt"
    if not r.is_file():
        raise HTTPException(404, "no REPORT.txt")
    return r.read_text()
