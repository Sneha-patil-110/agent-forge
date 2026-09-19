# API Design

## Overview

AgentForge has two independent interfaces to the same underlying `Application` (see [System_Architecture.md](System_Architecture.md)):

* **CLI** (`backend/cli/`) — the original interface. Five subcommands, synchronous, one process per invocation.
* **REST/SSE API** (`backend/api/`, added in v0.11) — FastAPI, one long-lived server process, long workflow runs backgrounded on a thread pool so requests return quickly.

Neither wraps the other; both call the same `Application.start_run()`/`resume_run()`/`run_service`/`event_dispatcher`. There is no GraphQL and no WebSocket transport. A frontend exists (see [Frontend_Design.md](Frontend_Design.md)) and, as of v1.1, authenticates against every route below except health/version/auth itself.

---

# Part 1: CLI

```
agentforge create|resume|status|runs|inspect|docs|mcp
```

## `agentforge create "<request>"`

Creates a new run and executes the full workflow synchronously — the command blocks until the workflow reaches a terminal state (`COMPLETED` or `FAILED`) or is interrupted. Prints `Run ID: <id>` and `Status: <status>` as each event fires (via `CLIEventRenderer`), plus a final summary line.

## `agentforge resume <run_id>`

Resumes an interrupted run from its last LangGraph checkpoint, in a brand-new process if needed. If the run is already `COMPLETED`/`FAILED`, prints that and does nothing further (exit code reflects the existing terminal status).

## `agentforge status <run_id>`

Lightweight summary: run ID, status, created/updated timestamps, current step, current agent. Reads `state.json`/`metadata.json` directly via `RunService` — no LangGraph or agent machinery involved.

## `agentforge runs`

Lists every run under `.agentforge/runs/`, sorted most-recently-updated first. A run whose metadata/state fails to parse is listed with status `corrupted` rather than hidden.

## `agentforge inspect <run_id>`

Detailed, safe summary: everything `status` shows, plus project name, retry counts, testing/review results, and count of materialized files. "Safe" means no prompt text, no full generated source, no secrets — only structured summary fields.

## `agentforge docs <run_id> [path] [--metadata] [--output FILE]`

Lists or views a run's generated documentation, reading `WorkflowState.documentation` live (same source as `inspect`, no database dependency). Without `path`: a table of every generated doc (path, title, status — `generated` or `failed`, from `written_files`/`file_write_errors`). With `path`: prints that document's content to stdout, `--metadata` prints title/description/generating-agent/status instead, and `--output FILE` writes the content to a local file instead of stdout. An unknown `path` exits with code 2 (invalid argument).

## `agentforge mcp list|inspect|tools|test|health|refresh`

A nested subcommand group (`agentforge mcp <subcommand> ...`), backed by the same `MCPManagementService` as the REST API — reads real config/registry state, no separate implementation:

* `mcp list` — table of every configured server (ID, status, transport, tool count, auth type).
* `mcp inspect <server_name>` — full detail for one server; exits 2 if unknown.
* `mcp tools [server_name] [--query TEXT]` — registered tools, optionally scoped to one server and/or filtered by a name/description substring.
* `mcp test <server_name>` — runs a health check and prints the result; exits 0 only if the result is `online`.
* `mcp health [server_name]` — health check for one server, or every enabled server if omitted.
* `mcp refresh` — re-discovers tools for every enabled server, printing which ones were reachable.

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Unexpected/internal error (full detail goes to the log file) |
| 2 | Invalid arguments, including a malformed run ID or an unknown MCP server name |
| 3 | Run not found |
| 4 | Run metadata or state is corrupted |
| 5 | The workflow itself completed but ended in a `FAILED` status |
| 130 | Interrupted (Ctrl-C) |

These map directly from the same `AgentForgeException` hierarchy the REST API's error handler also uses (`backend/core/exceptions.py`) — `InvalidRunIdError`→2, `RunNotFoundError`→3, `RunCorruptedError`→4.

---

# Part 2: REST / SSE API

Run with: `uvicorn backend.api.app:app`. All resource endpoints are under `/api/v1`; `/`, `/health`, `/version` are unversioned.

## Response Envelope

Success responses are the Pydantic response model directly (no `{"success": true, "data": ...}` wrapper). Every error response, regardless of source (`AgentForgeException` subclass, a plain `HTTPException`, request validation, or an unhandled exception) has the same shape:

```json
{
    "error": {
        "type": "RunNotFoundError",
        "message": "Run not found: af_20260717_deadbeef"
    }
}
```

Internal detail (tracebacks, file paths) is never included in a response — only `AgentForgeException.message` (already written to be a safe, user-facing string throughout the codebase) or a generic fallback for unexpected errors. Full detail still goes to the server log. See `backend/api/errors.py`.

## Status Code Mapping

| Exception | HTTP Status |
|---|---|
| `InvalidRunIdError` | 400 |
| `RunNotFoundError`, `ProjectNotFoundError`, `KnowledgeEntryNotFoundError`, `MCPToolNotFoundError`, `MCPServerNotFoundError` | 404 |
| `AuthenticationError`, missing/invalid bearer token | 401 |
| `AuthorizationError`, `MCPPermissionDeniedError` | 403 |
| `AgentValidationError`, `ValidationError`, request body validation | 422 |
| `InvalidRepositoryPathError` | 400 |
| `RepositoryPathNotFoundError` | 404 |
| `RepositoryPathAlreadyExistsError`, `RepositoryConflictError` | 409 |
| `RateLimitError` | 429 |
| `RunCorruptedError` | 500 |
| `ConfigurationError`, `DatabaseError` (includes "no database configured") | 503 |
| Any other unhandled exception | 500, generic message only |

A run owned by someone else — or with no owner at all (a CLI-created run has no user concept) — returns **404**, not 403: this is deliberate. Returning 403 confirms the run exists; 404 doesn't leak that. See "Authentication & Ownership" below.

## Health

| Method | Path | Returns |
|---|---|---|
| GET | `/` | `{"name": "AgentForge", "version": "0.11.0"}` |
| GET | `/health` | `{"status": "ok", "database": "connected" \| "unavailable"}` |
| GET | `/version` | `{"version": "0.11.0"}` |

## Runs

Every route below requires `Authorization: Bearer <token>` and is scoped to the authenticated user's own runs.

| Method | Path | Behavior |
|---|---|---|
| POST | `/api/v1/runs` | Body: `{"request": "<natural language>"}`. Rate-limited (`RATE_LIMIT_RUN_CREATION_PER_MINUTE`, default 5/min/user). Submits `Application.start_run(owner_id=current_user.id)` to a background thread; returns **202 Accepted** with `{"run_id", "status": "running"}` as soon as the run ID is known (`WORKFLOW_STARTED`), not when the workflow finishes. **v1.5**: `start_run()` is now a thin wrapper over `start_project_run(project_id=None, ...)` — every run created this way also gets a backing `Project` (see "Projects — Iterative Development" below), kept as a legacy/CLI-compatible entry point; the frontend's dashboard calls `POST /projects` instead. |
| GET | `/api/v1/runs` | Paginated/filterable/searchable/sortable list, backed by PostgreSQL (`RunRepository`), filtered to `user_id = current_user.id` — **503** if no database is configured. **v1.5**: query params expanded from just `?status_filter=`/`?limit=`/`?offset=` to also include repeatable `?status_filter=` (multi-select), `?q=` (matches run ID, current agent, `request_text`, or the owning project's name), `?date_from=`/`?date_to=` (range on `created_at`), and `?sort=` (`recently_updated` default, `newest`, `oldest`, `duration`, `status` — a needs-attention-first ordering: running, then waiting-for-user, then failed, then everything else). Response gained `total_count`/`has_more` for real pagination (previously just a flat `runs` array with no way to know if there were more). |
| GET | `/api/v1/runs/{run_id}` | Full detail, read live from `state.json`/`metadata.json` (never the database) — project name, testing/review result, files materialized, etc. **404** if the run isn't owned by the caller. |
| GET | `/api/v1/runs/{run_id}/status` | Lightweight status only, same live source as `agentforge status`. |
| POST | `/api/v1/runs/{run_id}/resume` | Rate-limited (`RATE_LIMIT_RUN_RESUME_PER_MINUTE`, default 10/min/user). If the run is already terminal, returns its current status immediately with no background work. **409** (`RunAlreadyResumingError`) if a resume for this run is already in flight. Otherwise submits `resume_run()` to the background thread and returns **202** with `status: "running"`. |

`POST /runs` never blocking for the workflow's duration is the key design decision here: a real multi-agent run can take minutes, and holding an HTTP request open for that long is fragile (proxies/load balancers time out, clients can't easily show progress). A client is expected to either poll `GET /runs/{id}/status` or subscribe to the SSE stream below.

**Concurrency note**: a lock is held internally for the few milliseconds between subscribing a `WORKFLOW_STARTED` listener and receiving it — without this, two `POST /runs` calls arriving concurrently could each capture the *other's* run ID, since a `WorkflowEvent` carries no per-request correlation ID of its own. This does not serialize the runs themselves (only their startup), verified by a test that fires 5 concurrent creates and asserts 5 distinct run IDs.

**Duplicate-resume guard (v1.4)**: `Application` tracks an in-memory set of run IDs currently being resumed (`is_resuming`/`mark_resuming`/`clear_resuming`, guarded by a `threading.Lock`). The router checks and marks synchronously, in the request thread, before submitting the background task — not inside `resume_run()` itself, which is untouched — so a second resume request for the same run arriving before the first has finished is rejected with 409 rather than invoking `graph.invoke()` twice concurrently for the same LangGraph checkpoint thread. This does **not** cover a run still executing its *original* `start_run()` pass (only a second `resume_run()` racing a first) — see [Future_Improvements.md](Future_Improvements.md) for why that narrower case was left out of scope.

## Events (Server-Sent Events)

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/v1/runs/{run_id}/events` | `text/event-stream`. Replays history first (from PostgreSQL, if configured — skipped gracefully otherwise), then live events for the rest of the connection. |

Each message is `data: {json}\n\n`, where the JSON is a `WorkflowEvent` (`event_type`, `run_id`, `agent`, `message`, `metadata`, `timestamp`; historical replay messages additionally include the database row `id`). A `: heartbeat\n\n` comment is sent every 15 seconds with no activity, to keep the connection alive through proxies. The stream ends on the next terminal event (`workflow_completed`/`failed`/`interrupted`) — including immediately after replay, if the last historical event was already terminal — or after a 30-minute hard cap. Built entirely on the existing in-process `EventDispatcher.subscribe()`/`unsubscribe()`; there is no message broker and no polling of PostgreSQL for new events.

**Single-process limitation**: because delivery is a direct in-process subscription, this only works correctly with exactly one API server process. See [Future_Improvements.md](Future_Improvements.md).

**Auth exception**: browsers' native `EventSource` cannot set an `Authorization` header, so this is the one route that also accepts the token as `?token=<jwt>`. Every other route requires the header. This is a deliberate, narrowly-scoped exception (`get_current_user_for_sse` — header preferred, query param as fallback) — URLs can end up in proxy/server logs, so the weaker posture is intentionally confined to this one endpoint. Ownership is enforced the same way as every other run-scoped route (404 for a run the caller doesn't own).

## Recovery & Failure Analytics (v1.6)

Every route below requires auth and is scoped to the caller's own runs/projects (404 otherwise). See [Agent_Design.md](Agent_Design.md#failure-classification-per-invocation-analytics-and-recovery-v16) for the classification/instrumentation this is built on.

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/v1/runs/{run_id}/failure` | Assembled failure summary: failed/last-successful agent, failure time, retry counts, classified `failure_category`/`recovery_reason`, provider/model/duration of the failing invocation, whether it repeats the previous attempt's failure signature, the latest checkpoint, and a confidence-scored `recommendation` (`null` when the run hasn't failed). |
| GET | `/api/v1/runs/{run_id}/checkpoints` | Every LangGraph checkpoint for this run, newest first, with a best-effort `node_name` (read from that checkpoint's own `execution.current_agent`) — the picker list for "Restart From Checkpoint". |
| GET | `/api/v1/runs/{run_id}/timeline` | Every `agent_invocations` row for this run, in order — agent, attempt number, status, duration, provider/model, failure category/reason. Powers the frontend's workflow timeline. |
| GET | `/api/v1/runs/{run_id}/logs` | Up to the most recent 500 lines of `logs/app.log` whose `run=<id>` marker matches (reliable since v1.6's structured logging stamps every line — see below). |
| POST | `/api/v1/runs/{run_id}/retry-agent` | Auto-selects the checkpoint immediately before the failure and resumes — see `Application.retry_failed_agent`. Same background-thread/202 pattern and duplicate-resume guard (`is_resuming`/`mark_resuming`) as `POST /runs/{run_id}/resume`. |
| POST | `/api/v1/runs/{run_id}/restart-checkpoint` | Body: `{"checkpoint_id": "<id>"}`. Same mechanism as retry-agent with a caller-chosen checkpoint. |
| POST | `/api/v1/projects/{project_id}/restart` | A fresh run from only the project's original prompt, workspace backed up first. **409** if the project's first run hasn't started yet (same guard as `POST /projects/{id}/messages`). |
| POST | `/api/v1/projects/{project_id}/duplicate` | A brand-new project seeded from the original prompt; the source project is untouched. |

`GET /runs`/`GET /runs/{id}` (`RunSummary`/`RunDetail`) gained a `project_id` field in v1.6 (nullable — best-effort, same on-disk-cache caveat as `RunMetadata.project_id` elsewhere in this doc) specifically so the frontend can decide whether to show the project-scoped restart/duplicate actions without a second round-trip.

**Structured logging.** `backend/core/logging.py`'s format string gained `run=%(run_id)s`, populated by a `logging.Filter` reading the same `run_id` `ContextVar` `Application._execute()` already sets — every log line emitted during a run's execution is now attributable, which is what makes `GET /runs/{id}/logs` a reliable filter instead of best-effort string matching.

## Reliability Dashboard (v1.6)

Read-only, owner-scoped aggregates over the `agent_invocations` table (one row per graph-node execution — see [Database_Design.md](Database_Design.md)). No cross-user access: every query joins through `runs.user_id`.

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/v1/reliability/summary` | Overall success rate, per-agent stats (success/failure counts, success rate, avg duration, avg input/output tokens), and failure-category/recovery-reason/provider breakdowns. |
| GET | `/api/v1/reliability/agents/{agent}` | Drill-down for one agent: its stats row, a recovery-reason breakdown scoped to that agent, and up to 20 recent failures (run ID, exception type, category/reason, error message, provider/model, duration). **404** for a name that isn't a real `AgentType` value. |

## Workflow Graph (v1.6.x)

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/v1/workflow/graph` | The real compiled graph's structure: `nodes` (canonical display order — `backend.graph.workflow.WorkflowNode`'s own declaration order, the same order `builder.py` registers nodes in), `edges` (`{source, target, conditional}`, read directly off a fresh `WorkflowBuilder(...).build().get_graph()` — pure structure introspection, no side effects), and `repair_nodes` (nodes with an outgoing edge back to an earlier stage, e.g. `debugger`/`reviewer`). Requires auth; the data itself isn't user-specific. |

Added specifically so the frontend's workflow-progress diagram (`AgentPipeline`) has a single, backend-authoritative source for node order instead of a hand-maintained duplicate TypeScript list — see "v1.6.x — Workflow Progress Graph Consistency Fix" in [Agent_Design.md](Agent_Design.md) and [Frontend_Design.md](Frontend_Design.md) for the bug this closes and why the duplication was the second contributing factor.

## Run Project Shadow (legacy, run-scoped)

Every route below requires auth and is scoped to the caller's own runs (404 otherwise). **Not** the `Project` grouping entity introduced in v1.5 (see "Projects — Iterative Development" below) — this is a per-run snapshot of `WorkflowState.project` and predates it; the backing DB table was renamed `generated_projects` in v1.5 to free the name, but these route paths/response shapes are unchanged.

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/v1/runs/{run_id}/project` | `WorkflowState.project` fields, read live. Response model `RunProjectOut` (renamed from `ProjectOut` in v1.5, same fields). |
| GET | `/api/v1/runs/{run_id}/files` | Paths + sizes of files `MaterializationService` actually wrote (`ImplementationState.written_files`), not just what the LLM proposed. Unchanged since v0.11 — still the flat, `written_files`-based read-only listing the Milestone-2 code viewer uses. For full CRUD, the tree, and live-filesystem accuracy (user-created/renamed/moved files, empty folders), use the Repository API below instead. |
| GET | `/api/v1/runs/{run_id}/files/{path}` | File content. `path` must appear in `written_files` **and** resolve (via `Path.resolve()` + `relative_to`) inside the run's own output directory — the same path-traversal defense `MaterializationService` itself applies when writing. |

## Projects — Iterative Development (v1.5)

**Project is the durable, continuable unit.** A run is now always a child of a project; sending a follow-up message continues the *same* project (same materialized workspace directory, same durable knowledge/architecture/conversation) via a **new** run, instead of starting over from an empty directory. See [Agent_Design.md](Agent_Design.md#iterative-development-v15) for how the Analysis agent merges a follow-up into the existing spec, and [Database_Design.md](Database_Design.md) for the schema. All paths are under `/api/v1/projects`; every route requires auth and is scoped to the caller's own projects (404, not 403, for a project owned by someone else — same posture as runs).

| Method | Path | Behavior |
|---|---|---|
| POST | `/api/v1/projects` | Body: `{"request": "<natural language>"}`. Creates a brand-new project (`Application.start_project_run(project_id=None, ...)`): allocates `workspace/<project_id>/` as the project's permanent output directory, creates the `projects` row, then behaves exactly like `POST /runs` (background thread, 202, returns as soon as `WORKFLOW_STARTED` fires). Response: `{"project_id", "run_id", "status": "running"}`. Rate-limited the same as `POST /runs`. |
| POST | `/api/v1/projects/{project_id}/messages` | Body: `{"message": "<follow-up request>"}`. The continuation endpoint: loads the project's `latest_run_id`'s final `WorkflowState`, seeds a new run via `RunService.seed_continuation_state()` (appends the message to `conversation.messages`; carries forward `project`/`planning`/`architecture`/`implementation.written_files`/`knowledge.entries`; resets `testing`/`debug`/`review` to fresh defaults and `execution.*` counters for a full new pass), pins the new run's `output_directory` to the *same* project directory, and executes it the same backgrounded way. **409** if the project's very first run hasn't reached `WORKFLOW_STARTED` yet (`latest_run_id` still null — a brief window right after `POST /projects` returns). |
| GET | `/api/v1/projects` | Paginated/filterable/searchable/sortable list of the caller's projects — same query param shape as the upgraded `GET /runs` above (`?status_filter=`, `?q=`, `?date_from=`/`?date_to=`, `?sort=`, `?limit=`/`?offset=`), backed by `ProjectRepository`. This is the dashboard's primary feed as of v1.5 (previously an unpaginated `GET /runs`). |
| GET | `/api/v1/projects/{project_id}` | `name`, `status` (denormalized from the latest run, refreshed by `DatabaseSyncService` on every snapshot event), `run_count`, `latest_run_id`, `initial_prompt`, timestamps. |
| PATCH | `/api/v1/projects/{project_id}` | Body: `{"name"}`. Renames. |
| DELETE | `/api/v1/projects/{project_id}` | Soft delete (`deleted_at`, not a hard delete) — `204`. A soft-deleted project is excluded from `GET /projects`/`GET /projects/{id}` (404) but its runs/files/DB rows are untouched, so this is recoverable in principle (no API exposes "undelete" yet). |
| GET | `/api/v1/projects/{project_id}/conversation` | The full merged conversation transcript: since `conversation.messages` is carried forward and appended run-over-run by `seed_continuation_state()`, the *latest* run's state already contains the complete history — this is a direct read (`RunService.load_state(project.latest_run_id)`), not an aggregation across runs. Each entry is `{"role": "human"|"ai", "content"}`. The `"ai"` turns are **synthesized**, not literal LLM chat output — see below. |

**Status filter vocabulary** (`?status_filter=`, shared by `GET /runs` and `GET /projects`): real `WorkflowStatus` values (`initialized`, `running`, `waiting_for_user`, `completed`, `failed`) plus two server-side pseudo-statuses that expand to a set of real ones — `resumable` → `initialized`/`running`/`waiting_for_user`, `interrupted` → `waiting_for_user` (the closest real match; `WORKFLOW_INTERRUPTED` is only ever a transient event, never a persisted status). **`cancelled` does not exist** — there is no cancellation plumbing anywhere in the graph/executor — and is rejected with **422**, not silently matched against nothing (`backend/repositories/status_filters.py::resolve_status_filter`).

**No free-text chat reply exists anywhere in the pipeline** — Analysis, Developer, etc. all produce structured JSON, never conversational prose. So when a run completes, `Application._execute()` synthesizes a short summary (files changed, test/review outcome, doc titles) as an `AIMessage` and appends it to `conversation.messages` *before* the final state is saved — this is what makes the conversation durable (survives a page refresh or backend restart) rather than reconstructed client-side from ephemeral SSE events, and why `GET .../conversation` needs no separate synthesis step of its own.

**Not built**: true token-by-token streaming of the assistant's reply (the pipeline produces structured JSON per stage, not incremental prose — building real LLM streaming would mean adding it to `LLMService` and every agent, a materially larger change); true conditional graph stage-skipping for narrow follow-ups like "fix this bug" (every follow-up still runs the full Analysis→Documentation pipeline — see [Agent_Design.md](Agent_Design.md#iterative-development-v15) for the "intent-scoped full pass" approach actually used instead); CLI support for creating/continuing a project (`agentforge create` still only does the v0.7-style one-shot `start_run()`; no `agentforge continue <project_id> "<message>"` subcommand exists yet).

## Knowledge

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/v1/runs/{run_id}/knowledge` | Auth required, scoped to the caller's own run. Filterable by `?category=`/`?status=`, backed by PostgreSQL (`KnowledgeRepository`) — mirrors `WorkflowState.knowledge.entries` as recorded by `KnowledgeManager`. See [Agent_Design.md](Agent_Design.md#shared-project-knowledge). |

## Repository (v1.1)

Full file/folder CRUD, search, diff, metadata, and documentation retrieval for a run's output directory — the backend counterpart to the frontend's Monaco-based repo explorer. Every route requires auth and is scoped to the caller's own run (`Depends(get_owned_run)`, same as every route above). All paths are under `/api/v1/runs/{run_id}/repo`.

| Method | Path | Behavior |
|---|---|---|
| GET | `/tree` | Recursive listing, live `Path.iterdir()` scan of the run's output directory (folders before files, then alphabetical) — not `written_files`, so it reflects renames/moves/user-created files/empty folders correctly. |
| GET | `/files/{path}` | Read a file's content, plus a content-hash `version` for optimistic-concurrency checks on the next write. **400** if the file isn't valid UTF-8 text (binary/image/compiled asset) — this API only ever serves text. |
| POST | `/files` | Create a file. Body: `{"path", "content"}`. **409** if it already exists. |
| PUT | `/files/{path}` | Overwrite a file's content. Optional `expected_version` (the `version` from a prior read) — **409** if the file changed since, so a stale edit is never silently clobbered. |
| DELETE | `/files/{path}` | Delete a file. |
| POST | `/files/{path}/rename` | Body: `{"new_name"}`. Renames within the same folder. |
| POST | `/files/{path}/move` | Body: `{"destination"}`. Moves to any path in the tree. |
| POST | `/files/{path}/duplicate` | Body: `{"destination"}`. Copies content and version history forward. |
| GET | `/files/{path}/metadata` | Size, language (by extension), last-modified time, `generated_by_ai` (true iff no version-history row exists — i.e. no API write has ever touched it), `last_edited_by`, `agent` (`"developer"`/`"documentation"`/`null`, by cross-referencing `ImplementationState.written_files`/`DocumentationState.generated_docs`). |
| GET | `/files/{path}/versions` | Append-only edit history for the file (`FileVersionRecord`): id, source (`generated`/`user_edit`), editor, timestamp. |
| GET | `/files/{path}/diff?from=<id\|"current">&to=<id\|"current">` | Raw content of two versions (a stored version ID or the literal `current` for live disk content) — **not** a computed diff. The frontend's Monaco Diff Editor consumes both strings directly and computes the diff client-side. |
| POST | `/folders` | Body: `{"path"}`. **409** if it already exists. |
| DELETE | `/folders/{path}` | Recursive delete. |
| POST | `/folders/{path}/rename` | Body: `{"new_name"}`. |
| POST | `/folders/{path}/move` | Body: `{"destination"}`. |
| GET | `/search?q=&mode=filename\|content\|fuzzy&language=` | `filename`: substring match against file **and folder** names/paths. `fuzzy`: subsequence (fzf-style) match against path, ranked by match tightness. `content`: per-line substring match in file contents (skips unreadable/binary files). All optionally filtered by `language`, capped at 100 matches. |
| GET | `/documentation` | The Documentation agent's generated docs for this run (`WorkflowState.documentation.generated_docs`), read live — same source `agentforge inspect` would show, not a separate store. Each entry is enriched with DB-backed fields (`generating_agent`, `status`, `created_at`, `updated_at`) from `documentation_files` when available; these are `null` if no database is configured or the doc hasn't been synced yet, but `content` is always present regardless. |
| GET | `/documentation/{path}/download` | Same file's raw content as an attachment (`Content-Disposition: attachment`), for direct browser download rather than inline display. |

All mutating routes validate the path first (`validate_repository_path`): rejects empty paths, path traversal (`..`), any rooted path (both drive-absolute *and* POSIX-style `/etc/passwd` — the latter isn't `Path.is_absolute()` on Windows but still escapes the workspace when joined with a base directory, so the check also rejects any path with a root component), overlong segments, invalid characters, and Windows-reserved names (`CON`, `PRN`, `NUL`, `COM1-9`, `LPT1-9`). Every actual filesystem operation goes through the existing `FilesystemTool` (extended with `move`/`copy`/`rmdir` for this batch) — its own workspace-boundary and `backend/`-source-tree guards apply on top of this validation, not instead of it. `RepositoryService._resolve()` additionally re-checks that the *resolved* (symlink-followed) path is still inside the *resolved* workspace root — `Path.resolve()` follows symlinks, so a symlink planted inside a run's output directory pointing outside it (e.g. at `backend/.env`) is caught here, both for reads/metadata and for `GET /tree`'s directory scan, before any content could be returned or listed. Every mutation also emits a `WorkflowEvent` (`FILE_CREATED`/`FILE_MODIFIED`/`FILE_DELETED`/`FILE_RENAMED`/`FOLDER_CREATED`/`FOLDER_DELETED`) through the same `EventDispatcher` the workflow itself uses — delivered over the same SSE stream as agent events, not a second event system.

**Diff against the original AI-generated content**: the first time a file with no existing version history is edited via `PUT /files/{path}`, the pre-edit on-disk content is snapshotted as a `source="generated"` baseline version *before* the new content is written and snapshotted as `source="user_edit"` — this is what makes "original generated ↔ edited" a real diff comparison, not just edit-to-edit, for files `MaterializationService` wrote directly (which are never snapshotted at generation time). A file created and then edited entirely through the API already has a `user_edit` version from `POST /files`, so no synthetic baseline is inserted for it.

## Documentation Persistence (v1.2)

Generated documentation is a first-class project artifact, not transient in-memory state — it's just a regular file under the run's output directory, so **every route above already works on it with no special-casing**: `GET /repo/tree` lists `docs/*.md` and `README.md` alongside source files, `GET/PUT/DELETE /repo/files/{path}` read/edit/delete them, `POST /repo/files/{path}/rename` and `/move` relocate them, `GET /repo/search` (filename, fuzzy, and content modes) finds them, and `GET /repo/files/{path}/diff` diffs an edited doc against its originally-generated content using the same baseline-snapshot mechanism as any other file.

What's documentation-specific is durability of *identity and generation metadata*, which lives in `documentation_files` (PostgreSQL) — see [Database_Design.md](Database_Design.md). This is populated by `DatabaseSyncService` whenever a `DOCUMENTATION_GENERATED` event fires (added to `_SNAPSHOT_EVENTS`), reading `WorkflowState.documentation.generated_docs`/`written_files`/`file_write_errors` the same way it already reads `state.project`/`state.knowledge` for every other snapshot event — no second sync mechanism. Only docs that were actually written (or attempted and failed) get a row; a doc merely *proposed* by the agent before materialization runs has nothing to sync yet. `RepositoryService` keeps this table consistent with disk: deleting a doc file via the generic delete route removes its record, renaming/moving one updates its `path` — both best-effort, wrapped in the same DB-optional try/except pattern used throughout this service, so a database outage never blocks the file operation itself.

**CLI**: `agentforge docs <run_id>` lists a run's generated docs (path, title, status) reading `WorkflowState.documentation` directly, the same live source `agentforge inspect` uses — no database dependency. `agentforge docs <run_id> <path>` prints one document's content (or `--metadata` for title/description/generating-agent/status, or `--output FILE` to write it to a local file instead of stdout).

**Resume and restart**: `WorkflowNodes.documentation()` now captures `state.documentation.written_files` *before* the agent runs and passes it as `previous_written_files` into `materialize_documentation()` — the same carry-forward pattern `materialize()` already used for the Developer agent. Without this, a workflow resume (or any regeneration) that reaches the documentation node again and produces fewer docs than a prior attempt would report a shrunken `written_files` list even though the earlier files are still on disk. Backend process restarts don't affect any of this: generated files live on the filesystem and `documentation_files` rows live in PostgreSQL, both independent of the API process's lifetime.

## MCP Management (v1.4)

Read-only inspection/administration over the existing MCP client/discovery/registry stack (`backend/mcp/`) — adds no new connection or tool-calling logic; `MCPManagementService` (`backend/services/mcp_management_service.py`) only composes what already existed. Global, application-level config (servers are declared in `backend/mcp/config/mcp_servers.yaml`, not per-run), so every route below just requires a valid authenticated user — there's no ownership dimension the way there is for runs/repository. All paths are under `/api/v1/mcp`.

| Method | Path | Behavior |
|---|---|---|
| GET | `/servers` | Every configured server (including disabled ones), each with connection status, transport, endpoint, auth type/configured-flag, tool count, and the most recent cached health-check result (`null` fields if never checked). |
| GET | `/servers/{server_name}` | Same shape, one server. 404 if unconfigured. |
| GET | `/servers/{server_name}/tools` | Tools currently registered for one server (from the in-memory `MCPToolRegistry` — run `/refresh` first if it's empty). |
| GET | `/tools?q=` | Every registered tool across all servers, optionally filtered by a case-insensitive substring match against tool name or description. |
| POST | `/servers/{server_name}/health-check` | Connects (or reuses a cached connection), pings, and records latency + server version (from the MCP `initialize` handshake) if reachable. Maps failures to a specific status — `online`/`offline` (disabled)/`unreachable`/`authentication_failed` (HTTP 401/403)/`timeout` — never a raw exception. Result is cached and reflected in subsequent `GET /servers` calls. |
| POST | `/refresh` | Re-discovers tools for every *enabled* server and replaces (not merges into) each server's prior tool set in the registry, so a tool a server no longer offers doesn't linger as stale. A server that fails to connect is skipped, not fatal to the others. Returns the list of servers actually refreshed. |

**Never exposed, by design**: no route ever returns a credential value. `MCPServerAuth.credential_env_var` names an environment variable to resolve *at connection time* — mirroring `MCPServerConfig.env`'s existing pattern of storing a variable *name*, never a secret — and only `auth_type` + `auth_configured: bool` (whether that env var is set) ever leave the service layer.

**Remote authentication**: `MCPServerConfig.auth` (new field) supports `api_key`/`bearer`/`custom_header` today, each resolving to an HTTP header (`Authorization: Bearer <token>`, or a configurable header name for the other two) built at transport-construction time via `resolved_auth_headers()` and passed to FastMCP's `StreamableHttpTransport(headers=...)`. `oauth`/`mtls` are declared in the `MCPAuthType` enum (so a management UI can already show them as a configured *type*) but have no transport wiring yet — genuinely future-ready, not silently broken. Auth is rejected at config-validation time for `stdio` transport (meaningless there; `stdio`'s own credential mechanism remains `env`, unchanged).

**Health status values**: `online`, `offline` (server disabled), `unreachable` (connection/transport failure), `authentication_failed` (HTTP 401/403 from a remote server), `timeout`, `disabled`. Health results are cached in-memory per `MCPManagementService` instance — single-process only, matching this codebase's existing SSE/rate-limiter precedent — and are only ever populated by an explicit health-check call (`POST /servers/{name}/health-check`, `POST /refresh`, or the CLI's `mcp health`/`mcp test`); nothing polls automatically yet.

## Auth

Email is the sole account identifier as of v1.7 — there is no username field anywhere in the schema or API; `users.id` (UUID) remains the actual database primary key and the only thing foreign keys reference.

| Method | Path | Behavior |
|---|---|---|
| POST | `/api/v1/auth/register` | `{"email", "password"}` → creates a `User` row (bcrypt-hashed password). 409 on duplicate email. Public. |
| POST | `/api/v1/auth/login` | `{"email", "password"}` → `{"access_token", "token_type": "bearer"}` (JWT, HS256, `JWT_SECRET` from `.env`). Public. |
| GET | `/api/v1/auth/me` | Requires `Authorization: Bearer <token>`; returns the authenticated user. |

## Authentication & Ownership (v1.1)

As of v1.1, every route above except `/`, `/health`, `/version`, and `/api/v1/auth/*` itself requires `Authorization: Bearer <token>`, reusing the same JWT foundation `auth/login` already issued (`AuthService`, `HTTPBearer`) — no second auth implementation. `get_current_user` decodes the token and loads the `User` row; routes that previously took a bare `run_id` path param now take `metadata: RunMetadata = Depends(get_owned_run)` instead, which loads the run and checks ownership in one step.

**Ownership model**: every run created via the API is stamped with the creating user's ID at creation time — `RunMetadata.owner_id` (file-based, source of truth; `None` for CLI-created runs, which have no user concept) is mirrored into `RunRecord.user_id` (PostgreSQL, `runs.user_id` — added in the `8a037aad2678` migration) so `GET /runs` can filter efficiently at the database layer. Single-run ownership checks (`GET /runs/{id}`, `/status`, `/resume`, `/project`, `/knowledge`, `/events`, everything under `/repo`) use the file-based `owner_id` — no database round-trip needed, since these routes already load `RunMetadata` for other reasons. A run with no owner, or owned by a different user, returns **404** — never 403 — so existence isn't leaked.

**Rate limiting**: in-memory, sliding-window (`RateLimiter`, `backend/services/rate_limiter.py`), keyed per-user per-action (`f"run-creation:{user_id}"`). Configurable via `Settings.RATE_LIMIT_RUN_CREATION_PER_MINUTE` (default 5) and `RATE_LIMIT_RUN_RESUME_PER_MINUTE` (default 10) — not hardcoded into the route. Single-process only, matching this codebase's existing SSE-delivery limitation; Redis was explicitly out of scope for this batch. Applied via router-level `dependencies=[Depends(enforce_run_creation_rate_limit)]` on `POST /runs` and `POST /runs/{id}/resume`, so it runs before the handler body — exceeding the limit returns **429** before any run-creation work starts.

## CORS

Configured via `API_CORS_ORIGINS` (`Settings`, default `["http://localhost:3000"]`), matching `next dev`'s default port for local development. In production it's set to the deployed frontend's exact origin — required because `allow_credentials=True` and browsers reject wildcard origins on credentialed requests — see [Deployment.md](Deployment.md#cors) for the live configuration and [Frontend_Design.md](Frontend_Design.md) for the frontend side.

## Dependency Injection

FastAPI's own `Depends()` throughout `backend/api/dependencies.py`:

* `get_application` — returns the single `Application` built once at server startup (ASGI `lifespan`); overridden wholesale in tests with a lightweight fake so tests never construct the real, expensive `Application`.
* `get_db_session` — a per-request SQLAlchemy `Session`, committed/rolled-back/closed by the dependency itself; raises a clean `503` if no database is configured.
* `get_executor` — the shared `ThreadPoolExecutor` long-running workflow calls are submitted to.
* `get_current_user` — decodes and validates a bearer token (header only); required by every protected route.
* `get_current_user_for_sse` — same, but also accepts `?token=` as a fallback; used only by the events route (see "Auth exception" above).
* `get_owned_run` — loads `RunMetadata` for `run_id` and enforces ownership against `get_current_user`; the standard way every run-scoped route gets its metadata now.
* `enforce_run_creation_rate_limit` / `enforce_run_resume_rate_limit` — check `application.rate_limiter` before the route body runs; raise `RateLimitError` (→ 429) over the configured per-user limit.

## Design Principles

* The API never reimplements workflow logic — every route calls into `Application`, `RunService`, `EventDispatcher`, or a repository; nothing duplicates what those already do.
* Long-running work (a full multi-agent workflow) is always backgrounded; no HTTP request blocks for more than a database read, a file read, or the brief run-ID-capture window.
* Every error, from every layer, reaches the client in one consistent shape.
* The database is optional everywhere it's used; a route that genuinely requires it (list runs, knowledge, file versions/diff) fails clearly with 503 rather than crashing or returning wrong data.
* Auth and ownership are enforced uniformly via shared dependencies (`get_current_user`, `get_owned_run`), not re-implemented per route — every protected route composes the same building blocks.
* Repository mutations never bypass `FilesystemTool`; the API layer validates and authorizes, `RepositoryService` orchestrates, `FilesystemTool` is the only thing that ever touches disk.