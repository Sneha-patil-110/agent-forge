# AgentForge — quick demo

## 1. One-time setup (needs real internet, not this sandbox)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# fill in: GOOGLE_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, JWT_SECRET
```

No `DATABASE_URL` needed for a bare demo — the app runs without a DB, just
without run history/persistence.

## 2. Start the backend

```bash
uvicorn backend.api.app:app --reload
```

Docs / manual API poke: http://127.0.0.1:8000/docs

## 3. Start the frontend (separate terminal)

```bash
cd frontend
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open http://localhost:3000

## 4. Demo run — keep it small to respect token limits

Use a deliberately tiny prompt so the 8-agent pipeline (analysis -> planner ->
architect -> developer -> tester -> [debugger loop] -> reviewer ->
documentation) finishes in the fewest possible tool/model calls:

```
Build a single FastAPI endpoint GET /ping that returns {"status": "ok"}.
```

Avoid anything that invites multiple debug/retry cycles (e.g. "with tests,
Docker, auth, and a database") — each Tester failure re-invokes Debugger +
Developer, which is where token usage multiplies fastest.

## 5. What to point out live

- Analysis/Tester calls go to **NVIDIA NIM** (`openai/gpt-oss-20b`) and
  Summarizer goes to **Groq** (`llama-3.1-8b-instant`) — both fast, generous
  free tiers; watch these return almost instantly in the SSE stream.
- Planner/Reviewer/Documentation go to **Gemini**.
- Architect/Developer/Debugger — the roles that most need strong reasoning —
  go to **OpenRouter** (Claude Sonnet / Qwen3 Coder / DeepSeek R1).
- 4 providers total spreads every role's token usage so no single provider's
  free-tier/rate limit carries the whole pipeline.
- Everything streams live over SSE: agent status, file diffs, test output.

## 6. If a provider free tier gets rate-limited mid-demo

Swap that one role in `backend/llms/config/models.yaml` to another already-
configured provider (e.g. move `tester` from `groq` to `google`) — no code
change needed, just edit the YAML and restart the backend.

## Known gaps (say this proactively, don't let it surprise you live)

- No `.env.example` existed before this session — now added.
- `RATE_LIMIT_RUN_CREATION_PER_MINUTE=5` — don't kick off more than 5 runs/min
  or you'll hit AgentForge's own limiter, separate from provider limits.
- `playwright` MCP server doesn't work in cloud/sandboxed environments,
  per the project's own `docs/Future_Improvements.md` — fine locally.
