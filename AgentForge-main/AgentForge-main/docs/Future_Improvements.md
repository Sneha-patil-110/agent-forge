# Future Improvements

## What This Document Is

Concrete, known limitations and technical debt items across the current implementation — as opposed to [Development_Roadmap.md](Development_Roadmap.md), which tracks new capabilities/phases. Everything here was identified and explicitly disclosed during the batch that introduced it, not discovered later; each item names the doc/report where it was first written down.

---

## MCP

* **Per-call reconnect overhead.** `MCPToolExecutor.execute()` calls `asyncio.run()` once per tool call; a connection may be transparently re-established each time rather than persisted across calls, since FastMCP connections don't reliably survive separate event loops. Correctness is unaffected; a persistent background event loop would be the fix if call volume ever makes this matter. (`MCP_Integration.md`, `summary/v09_summary.md` §26)
* **`oauth`/`mtls` auth types declared but not wired.** `MCPAuthType` (v1.4) has both as real enum values a config file can already declare, but `resolved_auth_headers()` produces nothing for them — only `api_key`/`bearer`/`custom_header` actually build a transport header today.
* **No automatic MCP health polling.** A server's cached status only refreshes on an explicit health-check/refresh call (API, CLI, or the frontend's manual buttons) — never on a timer. (v1.4)
* **stdio and HTTP transports only** — no SSE transport, no in-process FastMCP transport wired for production use.
* **Single agent has MCP access.** Extending beyond Documentation is supported by the permission model but requires a deliberate per-agent risk review, not just a config change (`Agent_Design.md`).
* **No remote MCP tool-execution UI.** The v1.4 management surface (page + CLI) is inspection/administration only, by design — there's no way to manually invoke a tool outside of an agent actually calling it.
* **`playwright` cannot connect in the FastAPI Cloud environment (v1.7).** It's the one remaining `npx`-launched MCP server; real browser automation needs Chromium/Firefox binaries plus Linux system libraries (`libnss3`, `libatk-bridge2.0-0`, `libgbm`, etc.) that no Python-only, Dockerfile-less environment can install. The other three previously-`npx`-based servers (`filesystem`, `sequential-thinking`, `postgres`) were reimplemented without a Node dependency specifically to work around this; `playwright` has no equivalent path since the fix isn't "avoid Node," it's "get real browser binaries + OS libraries installed," which needs Docker/apt-level access this environment doesn't expose. Works locally and in the project's own Docker image. (`MCP_Integration.md`, `Deployment.md`)

## API / SSE

* **Single-process SSE delivery.** Event streaming subscribes directly to the in-process `EventDispatcher` — correct for exactly one API server process. A horizontally-scaled deployment would need a shared pub/sub layer (Redis is the natural candidate; already a dormant dependency). (`API_Design.md`, `Database_Design.md`)
* **Single-process rate limiting (v1.1).** `RateLimiter` is an in-memory, per-process sliding window — correct for exactly one API server process, same limitation as SSE delivery above. A horizontally-scaled deployment would need a shared store (Redis, again the natural candidate). (`API_Design.md`)
* **SSE query-param auth is a narrower posture than header auth.** The events route accepts `?token=<jwt>` because `EventSource` can't set headers — a real, deliberate tradeoff (the token can end up in proxy/server logs) confined to that one route. (`API_Design.md`)
* **Background execution has no persistence of its own.** If the API process crashes while a run is executing in a background thread, that specific in-memory execution is lost — the run's `state.json`/checkpoint reflects whatever was last saved, and `POST /runs/{id}/resume` can restart it from there, but there's no automatic "resume everything that was mid-flight on crash" behavior.
* **Single shared `ThreadPoolExecutor`** for all backgrounded runs (`_EXECUTOR_MAX_WORKERS = 8`) — a fixed concurrency ceiling with no queueing/backpressure signal back to the client beyond the request simply waiting longer at submission time.

## Database

* **No connection pooling tuning** beyond SQLAlchemy defaults + `pool_pre_ping=True` — untested under real concurrent load.
* **`workflow_events` grows unbounded** — no retention policy or archival for old runs' event history.
* **Redis remains unused** — declared in `requirements.txt`, no code imports it. Would matter for the multi-process SSE scenario above, or for multi-process rate limiting.
* **`file_versions` still can't diff between two successive agent-generated writes.** `MaterializationService` itself never snapshots (LLM-generated content is written directly to disk, not through the repository API). A `source="generated"` baseline is captured lazily on a file's *first* API-driven edit (the pre-edit content, right before the edit overwrites it) — so "original generated ↔ edited" now works — but if the Developer agent rewrites the same file twice during a repair cycle before any user ever touches it, the intermediate generated state is never captured; only the version immediately before the first user edit is. (`API_Design.md`)

## Provider / Model Layer

* **7 of 8 core agent roles use one provider (Mistral), Analysis uses Perplexity** despite the architecture being genuinely provider-agnostic (Anthropic/Cerebras/Google/Groq/OpenRouter/Z.AI adapters exist and are wired, just unused by default). No live tool-calling call against an unused provider has been exercised.
* **No automatic fallback** if a configured provider is unavailable — `LLMService.invoke()` raises `LLMError` rather than retrying against a different provider.

## Recovery & Reliability (v1.6)

* **Static validation is deliberately narrow.** Syntax/local-import/route-registration only — no Pydantic-schema-vs-SQLAlchemy-model cross-validation (the exact bug class that motivated this work), no relationship/migration validation, no general static analysis (mypy/ruff-in-the-loop). (`Agent_Design.md`, `Development_Roadmap.md`)
* **No third-party/stdlib import resolution.** Static validation only checks imports of modules the generated project itself defines — checking third-party/stdlib imports would run against AgentForge's own interpreter's installed packages, not the generated project's, producing false positives on legitimate imports. A real fix would need to introspect the generated project's own declared dependencies (`requirements.txt`/`pyproject.toml`), not AgentForge's environment.
* **Route-registration check is a yes/no, not a per-router mapping.** It only flags "no router is ever wired up at all," not "this specific router is missing from `include_router`" — per-file alias tracking across generated files was judged more likely to misfire (false positives) than to catch a real bug.
* **Workspace `.backups/` snapshots are write-only.** `restart_workflow` creates one before overwriting a project's workspace, but nothing reads it back — restoring from a backup is a manual filesystem operation today, not an API/UI affordance. (`Database_Design.md`)
* **"Retry Failed Agent" is not true isolated single-node execution.** The graph has one entry point; it's an auto-selected `restart_from_checkpoint` under the hood. Documented honestly in both the UI copy and `Agent_Design.md`, not disguised as something it isn't.
* **`recovery_mode_success_rates()` returns an empty mapping today** — recovery-mode *outcomes* (did a retry actually lead to a completed run?) aren't yet joined back from `RECOVERY_ACTION_TAKEN` events into a queryable form, so the recommendation engine's confidence blending currently always falls back to its fixed priors. The event is recorded; only the aggregation query is missing.
* **"Report Issue" has no real backend.** Scoped to a clipboard copy of a structured failure summary — no issue-tracker integration exists or is being built as part of this.
* **Reliability dashboard has no cross-user/admin view.** Every query is scoped to the requesting user's own runs, consistent with the rest of the API's ownership model — there's no aggregate, all-users view for an operator, which would need a distinct authorization model (not just a missing query param).
* **`GET /runs/{id}/logs` is a whole-file scan.** It reads and filters the entire `app.log` on every call rather than an indexed/streaming query — fine at this log volume, would need revisiting if log retention grows substantially.
* **Live end-to-end verification of the recovery mechanism used a real LangGraph checkpointer + real pytest execution with a scripted LLM, not a real provider.** The checkpoint `get_state`/`update_state`/`as_node` mechanism itself is proven against real infrastructure (`tests/test_recovery_checkpoint.py`); a full live run through `Application` against a real LLM provider, the way v1.5's continuation feature was validated, was not additionally exercised for this batch given the scope already covered by the integration test.

## Deployment

* **No CI.** No `.github/workflows/` exists; both the FastAPI Cloud and Vercel deploys build directly from a push to `main` with no automated test gate in between. (`Deployment.md`)
* **No staging environment.** One production deployment per side (backend, frontend); nothing to validate a change against before it reaches `main`. (`Deployment.md`)
* **`GitTool` is non-functional in the FastAPI Cloud environment.** `GIT_PYTHON_REFRESH=quiet` avoids an import-time crash (GitPython eagerly checks for the `git` binary on `PATH`) but doesn't make git operations work — a disclosed, accepted tradeoff, not a bug. Unaffected locally and in the Docker image, which does install `git`. (`Deployment.md`)
* **Single instance, both sides.** Neither FastAPI Cloud nor Vercel runs multiple regions/instances of this app, compounding the single-process SSE delivery and rate-limiting limitations above if load ever grows. (`Deployment.md`)

## Testing

* **No live LLM calls in the automated test suite**, by design (cost, determinism) — every agent/LLM-calling code path is tested against real infrastructure *except* the model call itself (real FastMCP servers, real PostgreSQL, real SQLite checkpoints; a scripted/fake model response shaped exactly like a real one). This is a deliberate, disclosed trade-off, not an oversight, but it does mean a genuine provider-side behavior change (e.g. a different `tool_calls` response shape) would not be caught automatically.
* **No load/performance testing** of the API layer under concurrent runs.

---

## How Items Leave This List

An item moves out of this document when it's fixed and the fix is verified by the same standard every batch in [Development_Roadmap.md](Development_Roadmap.md) uses: full test suite passes, a written report, zero regressions.