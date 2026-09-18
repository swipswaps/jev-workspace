JEV WORKSPACE
=============

A local AI operating environment where Jev (TypeSafe AI's System One
model) is the structured judgment layer, SQLite + FTS5 is the evidence
layer, and opencode is the coding agent.

ARCHITECTURE

  CHAT LOG -> deterministic parser -> SQLite + FTS5 -> Jev judgments -> opencode

  evidence/raw/         immutable transcripts
  evidence/normalized/  parsed turns, JSONL
  evidence/derived/     audit reports

QUICK START

  export TYPESAFE_API_KEY="ts_..."     (optional; JEV_MOCK=1 works without)
  bash scripts/start.sh
  python3 scripts/ingest.py <chatlog.txt> <conversation_id>
  bash scripts/audit.sh
  npm install
  npm run dev

Backend listens on port 8787. Vite dev server on 5173. Same-origin, so
no Local Network Access prompt.

JEV QUESTION PRIMITIVES

  noul     0.0 to 1.0 probability    yes/no, verification
  choice   key + probabilities       routing, classification
  score    level + probabilities     severity, ranking

ENVIRONMENT VARIABLES

  TYPESAFE_API_KEY    required for real Jev calls
  TYPESAFE_BASE_URL   default https://api.typesafe.ai
  TYPESAFE_PATH       default /ask
  JEV_MODEL           default jev-latest
  JEV_MOCK            1 = use deterministic mock responses (no key needed)
  EVIDENCE_ROOT       default $HOME/jev-evidence
  BACKEND_PORT        default 8787

ENDPOINTS

  GET  /health
  POST /ingest                   multipart form: file, source
  GET  /conversations
  GET  /turns/{conversation_id}
  GET  /search?q=<fts5 query>
  POST /jev/judge                body: ns, instructions, state, criteria
  GET  /jev/calls
  GET  /audit/runs
  GET  /audit/latest
  GET  /debug/formats/{cid}      diagnose parser format detection
  GET  /debug/raw/{cid}          first N lines of the raw file

REQUIREMENTS

  python3, node 20, npm, jq, curl, ss, sqlite3, sha256sum
  gh (optional, authenticated) for GitHub push
  opencode (optional) for the coding agent
