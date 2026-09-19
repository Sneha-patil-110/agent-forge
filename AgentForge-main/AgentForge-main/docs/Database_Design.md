# Database Design

## Overview

AgentForge has two persistence layers with clearly separated responsibilities:

* **Workflow persistence** — plain files on the local filesystem, organized per run under `.agentforge/runs/<run_id>/`, plus generated project output under `workspace/<run_id>/`. This is the **sole source of truth** for a run's actual state and the only thing `agentforge resume`/`POST /runs/{id}/resume` ever replay from. Unchanged since before PostgreSQL existed in this codebase.
* **Metadata persistence** — PostgreSQL, added in v0.11, holding a queryable index of runs, workflow events, project metadata, and project knowledge for the API layer. It is strictly additive: nothing about workflow execution, resume, or the CLI depends on it, and a missing or unreachable database degrades every dependent operation to a no-op rather than an error.

Redis is still declared in `requirements.txt` (a holdover from the original SaaS-platform plan — see [Project_Vision.md](Project_Vision.md)) but not imported by any code in `backend/` — see [Development_Roadmap.md](Development_Roadmap.md) for what would motivate adding it.

---

## On-Disk Layout

```text
<repository root>/
├── .agentforge/
│   └── runs/
│       └── af_20260717_a1b2c3d4/          # one directory per run (RunService.run_dir)
│           ├── metadata.json               # RunMetadata — run identity + timestamps
│           ├── state.json                  # full WorkflowState snapshot (human-readable)
│           └── checkpoints.sqlite           # LangGraph SqliteSaver — resume log
│
└── workspace/
    └── proj_20260719_e558f1d8/              # ProjectState.output_directory (v1.5: keyed by
        └── <materialized project files>     # project_id, not run_id -- see "Projects" below)
```

**v1.5 change:** `output_directory` used to be `workspace/<run_id>/` for every run. It is now `workspace/<project_id>/`, allocated once when a project is first created and reused by every subsequent run in that project (each follow-up message creates a *new* `run_id` but reuses the *same* `output_directory`), so `MaterializationService`'s existing additive write behavior (union with `previous_written_files`) accumulates a single, growing codebase across a project's whole lifetime instead of starting a fresh empty directory per message. Runs created before v1.5 keep their original `workspace/<run_id>/` directory — the migration backfill (below) does not move files on disk, only backfills the database's `projects`/`runs.project_id` linkage.

`RUNS_ROOT` and `WORKSPACE_ROOT` (`backend/core/workspace.py`) are both resolved relative to the repository root and created on import if missing. `SOURCE_ROOT` (`backend/`) is explicitly never a valid write target for any tool — this is enforced by the filesystem-sandboxing tools themselves, not just by convention.

---

## Run Identity

Run IDs are generated, never user-supplied, in the fixed format `af_YYYYMMDD_xxxxxxxx` (8 lowercase hex characters from `secrets.token_hex(4)`) — `backend/utils/run_id.py`. `validate_run_id()` rejects anything not matching this exact pattern, and `RunService.run_dir()` additionally resolves the path and checks it's still inside `runs_root` (`Path.relative_to`) before ever touching disk. Between the two, a crafted `run_id` cannot escape the runs directory (path traversal) and cannot reference an arbitrary filesystem location. `CheckpointService.checkpointer_for_run()` performs the identical validation independently before opening its own SQLite file.

`RunService.create_run()` retries up to 5 times on a same-second ID collision (`FileExistsError` from `mkdir(..., exist_ok=False)`) before giving up with a `RunError`.

---

## `metadata.json` — `RunMetadata`

```python
class RunMetadata(BaseModel):
    schema_version: int      # currently 1
    run_id: str
    created_at: datetime
    updated_at: datetime     # bumped by RunService.save_state() on every write
    owner_id: str | None     # v1.1: the API user that created this run, or None for CLI-created runs
    project_id: str | None  # v1.5: best-effort/cache-only -- see "Projects" below; the runs
                             # table column, not this field, is the source of truth for legacy runs
```

The only long-lived identity record for a run; `agentforge runs`/`status`/`inspect` all read this to display creation/update times without loading the full state. `owner_id` (added in v1.1) is the **source of truth** for API-route ownership checks — see "Authentication & Ownership" in [API_Design.md](API_Design.md). A CLI-created run has no owner and is therefore never reachable through any API route (a run with `owner_id: null` returns 404 for every user, not just non-owners).

---

## `state.json` — `WorkflowState`

The complete run state, serialized via `WorkflowState.model_dump_json(indent=2)` and read back with `model_validate_json()`. See [State_Management.md](State_Management.md) for the full schema. This file is:

* The source of truth for `agentforge status`/`inspect`/`runs`.
* **Not** used by `agentforge resume` — resume replays from `checkpoints.sqlite` instead (see below). `state.json` is written for human inspection and as the initial seed state at `create_run()` time; it is overwritten with the final state after every `graph.invoke()` call.
* Human-readable and diffable — deliberately not a binary or compressed format, since run states are small (single-digit KB to low hundreds of KB even with full generated source embedded) and inspectability was prioritized over size.

---

## `checkpoints.sqlite` — LangGraph Checkpointing

One SQLite database per run, created lazily by `CheckpointService.checkpointer_for_run()` via LangGraph's own `SqliteSaver`. This is what makes `agentforge resume <run_id>` work: LangGraph checkpoints `WorkflowState` after every node executes, keyed by `thread_id = run_id`, and `graph.invoke(None, config={"configurable": {"thread_id": run_id}})` resumes from the latest checkpoint rather than starting over.

Serialization uses a custom `JsonPlusSerializer` configured with an explicit allow-list of classes (`allowed_msgpack_modules`) — every Pydantic model and enum reachable from `WorkflowState` (collected recursively by walking `model_fields`), plus the concrete LangChain message classes (`HumanMessage`, `AIMessage`, `SystemMessage`, `ToolMessage`, `ChatMessage`, `FunctionMessage`). Nothing outside that closure can be deserialized from a checkpoint — in particular, no MCP client/connection object, since none of those types are ever fields on `WorkflowState` in the first place. This has been directly verified: a checkpoint written mid-run, after a real MCP tool call, resumed correctly in a brand-new process with a freshly constructed `MCPClientManager`.

Each `checkpointer_for_run()` call opens a **fresh SQLite connection** (`check_same_thread=False`) — nothing is cached across calls; a new one is created for every `graph_for_run()` invocation within `Application`.

**v1.6:** `CheckpointService.list_checkpoints()` and `Application.restart_from_checkpoint`/`retry_failed_agent` are the first code in this codebase to use LangGraph's checkpoint history as more than a single "resume from the latest" pointer — `graph.get_state()`/`graph.update_state()` (LangGraph's own supported "edit state and continue" API, not raw checkpoint-table access) let a run's `execution` field be reset (clearing a committed `FAILED` status and exhausted retry counts) at an arbitrary earlier checkpoint before resuming, which is what makes recovering from a retry-limit exhaustion possible at all — plain `resume_run()` refuses to touch a `FAILED` run since nothing about its on-disk state would differ on a second invoke. See "Observability & Recovery (v1.6)" in [Agent_Design.md](Agent_Design.md).

---

## Atomic Writes

Both `metadata.json` and `state.json` are written via `atomic_write_text()` (`backend/utils/atomic_io.py`): write to a same-directory temp file, `fsync`, then `os.replace()` onto the final path. This guarantees a reader never observes a partially-written file, and a crash mid-write leaves the previous version intact rather than a corrupted one — important since `state.json` can be several KB of nested JSON and is rewritten after every single node in the graph.

---

## Corruption and Error Handling

`RunService`/`CheckpointService` distinguish three failure modes, each mapped to a specific CLI exit code (see [API_Design.md](API_Design.md)):

* **`RunNotFoundError`** — the run directory or the specific file (`state.json`/`metadata.json`) doesn't exist.
* **`RunCorruptedError`** — the file exists but fails to parse (`OSError`/`ValueError` from `model_validate_json`) — e.g. truncated JSON from an interrupted write that somehow bypassed the atomic-write guarantee, or manual tampering.
* **`InvalidRunIdError`** — the supplied run ID doesn't match the fixed format, raised before any filesystem access is attempted.

---

## Materialized Project Output

`MaterializationService` writes `ImplementationState.generated_code` to real files under `workspace/<run_id>/` (`ProjectState.output_directory`, set once at `start_run()` time). This is the actual deliverable of a run — a real, runnable project on disk — separate from `state.json`'s in-JSON copy of the same file contents. `written_files`/`file_write_errors` on `ImplementationState` record what actually landed on disk, distinct from what the LLM proposed.

---

## What Is *Not* Persisted

By explicit design, nothing below is ever written to `state.json`, a checkpoint, PostgreSQL, or anywhere else on disk:

* MCP client connections, `MCPToolExecutor`, or any FastMCP `Client` object — recreated fresh every process start.
* `TracingService` / LangSmith spans — live only for the duration of a trace; LangSmith itself, not AgentForge, is the system of record for trace history.
* In-memory-only conversation summarization state (`ConversationState.summary` exists as a field but nothing currently populates it).
* Generated source code / project files — these live only on the filesystem (`workspace/<project_id>/`, v1.5 — see "On-Disk Layout" above) and in `state.json`'s `implementation.generated_code`; the `generated_projects`/`projects` tables (below) store metadata, never file contents.

---

## PostgreSQL Metadata Layer (v0.11)

### Purpose

A queryable index for the API layer — `GET /runs` (paginated/filterable listing), `GET /runs/{id}/events` (SSE history replay), `GET /runs/{id}/knowledge` — none of which are practical to serve efficiently by scanning every run directory on disk. It is explicitly **not** a replacement for `RunService`/`CheckpointService`: `GET /runs/{id}` and `GET /runs/{id}/status` still read live from `state.json` directly, exactly like the CLI's `agentforge status`/`inspect` always have, since that file is always the freshest and most authoritative source.

### How it's kept in sync

`DatabaseSyncService` (`backend/services/db_sync_service.py`) subscribes to the same `EventDispatcher` the CLI's `CLIEventRenderer` and LangSmith tracing already observe — no new event system, no polling. On every event it persists a `workflow_events` row; on a curated set of "snapshot-worthy" events (`WORKFLOW_STARTED`, `WORKFLOW_RESUMED`, `AGENT_COMPLETED`, `TESTING_PASSED`/`FAILED`, `REVIEW_PASSED`/`FAILED`, `WORKFLOW_COMPLETED`/`FAILED`/`INTERRUPTED`) it also re-reads the current `WorkflowState` via `RunService.load_state()` and upserts `runs`/`projects`/`knowledge_entries` from it. High-frequency events (`AGENT_STARTED`, `MCP_TOOL_CALL_*`) are still recorded as rows but don't trigger a state re-read, since nothing summary-worthy changed yet.

Every operation is wrapped so a database failure is logged and swallowed — verified directly by a test that makes the session factory raise on every call and confirms `handle_event()` still returns normally. This mirrors `TracingService`'s own optional-dependency posture exactly: a workflow run must complete identically whether or not PostgreSQL is reachable.

### Schema

| Table | Purpose | Key |
|---|---|---|
| `runs` | Denormalized run summary (status, current step/agent, retry counts, timestamps, owning `user_id`, and as of v1.5, `project_id` + `request_text`) | `run_id` (matches the `af_YYYYMMDD_xxxxxxxx` format from `backend/utils/run_id.py`) |
| `projects` | **v1.5, first-class grouping entity.** The durable, continuable unit a user actually works in: `name`, `initial_prompt`, denormalized `status`/`run_count`/`latest_run_id` (kept fresh by `DatabaseSyncService` on every snapshot event), `deleted_at` (soft delete) | `id` (`proj_YYYYMMDD_xxxxxxxx`, `backend/utils/project_id.py`) |
| `generated_projects` | **Renamed from `projects` in v1.5.** Per-run mirror of `WorkflowState.project` (name, description, tech stack, requirements, output directory) — a snapshot of one run's spec, *not* the grouping entity above. Kept because it predates v1.5 and nothing else needed changing about it, just the name, to free `projects` for the new entity | `run_id` (FK, also PK — one row per run) |
| `workflow_events` | Every `WorkflowEvent` ever emitted for a run, verbatim — including the v1.1 repository events (`file_created`/`modified`/`deleted`/`renamed`, `folder_created`/`deleted`, `documentation_generated`) | auto-increment `id`, FK `run_id` |
| `knowledge_entries` | Mirror of `WorkflowState.knowledge.entries` (`KnowledgeManager`'s records) | composite `(run_id, id)` — a `KnowledgeEntry.id` like `"AD1"` is only unique within one run, not globally |
| `users` | Auth (email, bcrypt hash) — enforced on every protected route as of v1.1; email is the sole login identifier as of v1.7 | UUID `id` |
| `file_versions` | v1.1: append-only edit history per file, written by `RepositoryService` on every API-driven create/update/duplicate (`source="user_edit"`) — the backing store for the diff API | auto-increment `id`, indexed `run_id` + `path` |
| `documentation_files` | v1.2: mirror of `DocumentationFile` *identity and generation status* (title, description, generating agent, status, timestamps) for docs the Documentation agent actually wrote — **not** content, which lives only on disk (`workspace/<project_id>/`) and in `state.json`, same as any other generated file | composite `(run_id, path)` — a run can have up to six generated docs |
| `agent_invocations` | **v1.6.** One row per graph-node execution (per attempt): agent, status, provider/model/token/character counts, and on failure `exception_type`/`failure_category`/`recovery_reason`/`error_message`/`stacktrace` (truncated)/`checkpoint_id`. Written by `backend/graph/builder.py`'s event wrapper via a new `AGENT_INVOCATION_RECORDED` event, not by `BaseAgent` — see "Observability" in [Agent_Design.md](Agent_Design.md). No `project_id` column, same reachable-via-join precedent as `documentation_files` | auto-increment `id`, indexed `run_id` and `(agent, status)` |

`runs.user_id` (nullable UUID, FK to `users.id`, added in v1.1) mirrors `RunMetadata.owner_id` — see the `metadata.json` section above for why the file-based field is authoritative and this column exists purely to make `GET /runs` filterable at the database layer.

**v1.5: Project is now a real, first-class entity, not just a run-shadow.** Before v1.5, this doc said "this codebase has no separate Project/Workflow entity distinct from a run" — that's no longer true. `projects.id` is a genuine parent: `runs.project_id` (nullable, FK) links every run to the project it belongs to, and one project accumulates many runs over its lifetime as the user sends follow-up messages (see "Iterative Development" in [API_Design.md](API_Design.md)). `documentation_files` still doesn't denormalize `project_id` onto every row, since it's already reachable via a join through `run_id` → `runs.project_id`, consistent with how `knowledge_entries`/`workflow_events` are keyed.

`runs.request_text` (v1.5) is the literal prompt/follow-up message that triggered that specific run, derived by `DatabaseSyncService` from `state.conversation.messages[-1]` at `WORKFLOW_STARTED` snapshot time (before any agent has run, the last conversation message is exactly the request that started it). It exists so `GET /projects`/`GET /runs` can search by prompt text without joining conversation state — no such field existed anywhere before v1.5, since a run's originating prompt was previously only recoverable by loading `state.json` and reading `conversation.messages[0]`.

All models live in `backend/db/models/`, kept deliberately separate from `backend/state/` (the Pydantic workflow-state models) — no persistence model reuses or subclasses a workflow-state model.

### Repository layer

`backend/repositories/` (`RunRepository`, `EventRepository`, `ProjectRepository`, `KnowledgeRepository`, `UserRepository`, `FileVersionRepository`, `DocumentationRepository`) is the only code that constructs a SQLAlchemy query. `DatabaseSyncService` and every API router call repository methods; neither ever imports `sqlalchemy.select`/`session.query` directly.

### Connection handling

`create_db_engine()` (`backend/db/base.py`) reads `DATABASE_URL` from `Settings` (`backend/core/config.py`, itself sourced from a gitignored `.env`), attempts one connection, and returns `None` on any failure — never raises. `Application.__init__` stores the resulting engine/session factory (or `None`) and passes it to `DatabaseSyncService`; `Application.shutdown()` disposes the engine if one exists. A FastAPI request that needs a database session (`get_db_session` dependency) raises a clean `503 Service Unavailable` if none is configured, rather than a confusing internal error.

### Migrations

Alembic (`alembic/`, `alembic.ini`), configured to read the same `Settings.DATABASE_URL` (or an `ALEMBIC_DATABASE_URL` override, used to point the same migration at a separate test database) rather than a hardcoded connection string. The initial migration (`alembic/versions/1f27a0d6c0a7_initial_schema.py`) was autogenerated from the ORM models and creates all five original tables. A second migration (`8a037aad2678_add_run_ownership_and_file_versions.py`, v1.1) adds `runs.user_id` (+ FK to `users.id`, + index) and the `file_versions` table. A third migration (`8a676672128b_add_documentation_files_table.py`, v1.2) adds the `documentation_files` table. A fourth migration (`a692fd3733d0_add_projects_table_and_run_project_.py`, v1.5) is the one migration in this list that isn't purely additive DDL: it **renames** the existing `projects` table to `generated_projects` (`op.rename_table`, preserving every row's data), **creates** a new `projects` table for the grouping entity, adds `runs.project_id`/`runs.request_text`, and then **backfills data** — for every pre-existing run, it best-effort loads that run's `state.json` (via `RunService`, safe to import from a migration since it's pure filesystem/Pydantic, no network/LLM calls), derives a project name from the run's first conversation message (or falls back to the run_id if the state file is missing/corrupted), and inserts one new `projects` row per run plus the matching `runs.project_id`/`request_text` update. This backfill is deliberately one-legacy-run-to-one-new-project (1:1, lossless) — verified live against the development database, correctly turning all 7 pre-v1.5 runs into 7 named projects. A fifth migration (`ac71fe1dae50_add_agent_invocations_table_and_widen_.py`, v1.6) widens `knowledge_entries.source_id`/`supersedes` from `VARCHAR(64)` to `VARCHAR(255)` (a real pytest node ID run live during v1.6 development, ~74 chars, hit the old limit and was silently swallowed by `DatabaseSyncService`'s best-effort sync — a confirmed production bug, now fixed) and `generated_projects.backend_tech`/`frontend_tech`/`database_tech`/`deployment_tech` from `VARCHAR(128)` to `VARCHAR(255)` (same unvalidated-LLM-free-text risk class, fixed preemptively), and creates the `agent_invocations` table. A sixth migration (`e84be6c413b4_add_mcp_executions_table.py`) adds the `mcp_executions` table. A seventh migration (`f3a9c1d7b2e4_drop_username_from_users.py`, v1.7) drops `users.username` and its unique index — email became the sole account identifier, see [API_Design.md](API_Design.md).

All seven migrations were applied to the primary, test, and production databases, matching the two-database pattern established in v0.11 (production added in v1.7 — see [Deployment.md](Deployment.md)). Future schema changes are expected to go through `alembic revision --autogenerate` + review, never manual `ALTER TABLE`.

### v1.6: recovery workspace backups

`Application.restart_workflow` (the "Restart Entire Workflow" recovery mode — see [Agent_Design.md](Agent_Design.md#observability--recovery-v16)) copies the project's existing workspace directory to `workspace/<project_id>/.backups/<old_run_id>/` before Developer overwrites it, using `shutil.copytree` with `.backups` itself excluded from the copy (so a second restart doesn't recursively back up the first backup). Best-effort: a failed backup is logged and does not block the restart, same posture as every other observational path in this codebase. Nothing else reads these backups today — recovering from one is a manual filesystem operation, not exposed through the API (see [Future_Improvements.md](Future_Improvements.md)).

---

## Future Direction

Redis (`requirements.txt`, unused) would be the natural next addition if the API layer needs SSE fan-out or rate limiting shared across multiple server processes. As of v1.1, rate limiting is implemented in-memory (`RateLimiter`, `backend/services/rate_limiter.py`) with the same single-process-only posture the SSE implementation already had — a deliberate, documented choice consistent with existing precedent, not an oversight. Multi-process/multi-instance deployment is explicitly out of scope for now — see [Development_Roadmap.md](Development_Roadmap.md) and [Future_Improvements.md](Future_Improvements.md).

The `users` table and `AuthService` are enforced on every protected route as of v1.1 — see "Authentication & Ownership" in [API_Design.md](API_Design.md).