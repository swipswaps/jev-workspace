JEV WORKSPACE
=============

A local AI operating environment where Jev (TypeSafe AI's System One
model) is the structured judgment layer, SQLite + FTS5 is the evidence
layer, and opencode is the coding agent.

ARCHITECTURE

  CHAT LOG
     |
     v
  deterministic parser  (no AI)
     |
     v
  SQLite + FTS5
     |
     v
  Jev judgments  (noul / choice / score)
     |
     v
  opencode agent

  evidence/raw/         immutable transcripts
  evidence/normalized/  parsed turns, JSONL
  evidence/derived/     audit reports

QUICK START

  export TYPESAFE_API_KEY="ts_..."
  bash scripts/start.sh
  python3 scripts/ingest.py <chatlog.txt> <conversation_id>
  bash scripts/audit.sh
  npm install
  npm run dev

The backend listens on port 8765. The Vite dev server listens on 5173.
Same-origin localhost, so no Local Network Access prompt.

JEV QUESTION PRIMITIVES

  noul     0.0 to 1.0 probability    yes/no, verification
  choice   key + probabilities       routing, classification
  score    level + probabilities     severity, ranking

OPENCODE

opencode reads opencode.json from the repo root and AGENTS.md for
project rules. Both are plain text. Agents are configured by editing
opencode.json.

ENVIRONMENT VARIABLES

  TYPESAFE_API_KEY    required for Jev calls
  TYPESAFE_BASE_URL   default https://api.typesafe.ai
  TYPESAFE_PATH       default /ask
  JEV_MODEL           default jev-latest
  EVIDENCE_ROOT       default $HOME/jev-evidence
  BACKEND_PORT        default 8765

WHAT JEV IS NOT

Jev is not a chatbot. It answers typed questions. Do not ask it to
generate prose. Use it for routing, classification, verification,
ranking, and gating. Application code owns the control flow.

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

REQUIREMENTS

  python3, node 20, npm, jq, curl, ss (iproute2)
  gh (optional, authenticated) for GitHub push
  opencode (optional) for the coding agent
