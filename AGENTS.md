AGENTS.md - Jev Workspace Rules

IDENTITY

This repository is a Jev workspace: a local AI operating environment
where Jev (TypeSafe AI's System One model) is the structured judgment
layer, SQLite + FTS5 is the evidence layer, and opencode is the coding
agent.

CORE RULES

1. Evidence first. Never overwrite evidence/raw/. All derived data
   lives in evidence/normalized/ and evidence/derived/.

2. Jev is not a chatbot. Jev answers typed questions. Never ask it to
   generate prose. Use it for routing, classification, verification,
   ranking, and gating.

3. Application code owns control flow. Jev returns probabilities. Your
   code decides thresholds and side effects.

4. Deterministic parsing before any AI. The chat log parser is pure
   Python. No model touches raw transcripts.

5. Audit before edit. Run bash scripts/audit.sh before modifying any
   tracked file.

6. No exit 1 in user-facing scripts. Use return 0 or fall through.

7. No 2>/dev/null. Redirect to a named file or /tmp/ path instead.

WORKFLOW

  INGEST -> NORMALIZE -> JEV JUDGE -> AUDIT -> EDIT -> VERIFY -> COMMIT

JEV QUESTION PRIMITIVES

  noul     0.0 to 1.0 probability    yes/no, verification
  choice   key + probabilities       routing, classification
  score    level + probabilities     severity, ranking

COMMANDS

  bash scripts/start.sh                                  start backend on :8787
  bash scripts/stop.sh                                   stop backend
  python3 scripts/ingest.py <file.txt> <conversation_id> ingest a chat log
  bash scripts/audit.sh                                  run audit
