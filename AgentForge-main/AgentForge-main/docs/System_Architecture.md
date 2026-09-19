# System Architecture

## Overview

AgentForge orchestrates eight specialized AI agents through a synchronous LangGraph workflow to turn a natural language software request into a generated, tested, reviewed, and documented project on disk. It has two entry points that share one composition root: a **CLI** (`backend/cli/`, the original interface) and a **FastAPI REST/SSE API** (`backend/api/`, added in v0.11) — both construct exactly one `Application` object (`backend/core/app.py`) and drive it in-process; neither depends on the other.

A single `Application` object is the composition root: it constructs every service, agent, and the compiled LangGraph graph once. Each run is identified by a `run_id` and persisted as plain files under `.agentforge/runs/<run_id>/` — a JSON snapshot of the workflow state plus a LangGraph SQLite checkpoint database — so a run can be resumed later, including in a brand-new process. Workflow execution itself remains fully synchronous (`graph.invoke`, never `ainvoke`); the API layer runs it on a background thread rather than making the workflow itself asynchronous.

Since v0.11, PostgreSQL holds a queryable *metadata index* — run summaries, workflow events, project metadata, project knowledge — kept in sync from the same `EventDispatcher` the CLI's own output rendering already uses. It is strictly additive: the database is optional (the CLI and the core workflow work identically with no database configured at all), and it is never the source of truth for a run's actual state or for resuming a workflow — see [Database_Design.md](Database_Design.md).

External capabilities beyond the four built-in tools (filesystem, terminal, git, search) are exposed to agents through the Model Context Protocol (MCP), via a real [FastMCP](https://github.com/jlowin/fastmcp) client integration. Only the Documentation agent currently has MCP tool access. LangSmith provides optional, fully-degradable tracing across every workflow, agent, LLM, tool, and MCP call. The language model layer is provider agnostic (Anthropic, Cerebras, Google, Groq, Mistral, OpenRouter, Perplexity, and Z.AI adapters all exist), configured per agent role via a YAML file.

---

## High Level Architecture

```text
      User (terminal)              HTTP client (curl, future frontend)
            │                                    │
   agentforge <command>                 FastAPI / SSE (backend/api/)
            │                                    │
      backend/cli/                    lifespan-constructed Application,
 (main.py, commands.py)                shared across every request,
            │                          long runs backgrounded on a
            │                          ThreadPoolExecutor (POST /runs)
            │                                    │
            └──────────────────┬─────────────────┘
                                ▼
                          Application
                    (backend/core/app.py — the
                     single composition root)
                                │
   ┌──────────────┬─────────────┼──────────────┬───────────────┬──────────────────┐
   ▼              ▼             ▼              ▼               ▼                  ▼
RunService  CheckpointService EventDispatcher TracingService DatabaseSyncService  AuthService
(JSON state, (LangGraph SQLite (in-process pub/  (optional     (subscribes to the   (JWT +
 run metadata) checkpoint per   sub, drives CLI   LangSmith     dispatcher; mirrors  bcrypt,
                run)            output + SSE)     spans)        runs/events/project/ optional
                                                                 knowledge into       foundation)
                                                                 PostgreSQL if
                                                                 configured)
                                │
                                ▼
                      Compiled LangGraph graph
        ┌──────────┬──────────┬───────────┬──────────┐
        ▼          ▼          ▼           ▼          ▼
    Analysis → Planner → Architect → Developer → Tester
                                         ▲            │
                                         │      pass  │  fail
                                    Debugger ◄─────────┘
                                         │
                              (retry Developer, bounded)
                                         │
                                         ▼
                                     Reviewer
                                pass  │      │ fail (retry Developer, bounded)
                                      ▼
                                Documentation
                          (only agent with MCP tool access)
                                      │
                                      ▼
                              Final WorkflowState
                        (persisted, files materialized
                         under workspace/<run_id>/)
```

Every node above shares one `WorkflowState` object, assembled per-agent by a centralized `ContextManager`, and can read/write a shared `KnowledgeState` via `KnowledgeManager`.

---

## Composition Root: `Application`

`backend/core/app.py`'s `Application.__init__` is the only place the system is wired together. In order:

1. `PromptService` — loads/caches prompt files from `backend/prompts/`.
2. `TracingService` — wraps LangSmith; a no-op when disabled.
3. `KnowledgeManager` and `ContextManager` — shared knowledge store and per-agent context assembly.
4. `ModelRegistry` / `LLMService` — provider-agnostic LLM access, model config from `backend/llms/config/models.yaml`.
5. `ToolRegistry` with the four internal tools registered (`FilesystemTool`, `TerminalTool`, `GitTool`, `SearchTool`).
6. `MaterializationService` and `TestingService` — Python-orchestrated file writing and real test execution (never delegated to the LLM).
7. MCP subsystem: `MCPClientManager`, `MCPToolRegistry` (tools discovered from any enabled server), `MCPPermissionPolicy` (deny-by-default; only `documentation.*` is granted, and only to the Documentation agent), `MCPToolExecutor`.
8. `EventDispatcher` — in-process pub/sub for `WorkflowEvent`s.
9. The eight agents, each constructed with `prompt_service`, `llm_service`, `context_manager`, `knowledge_manager`; only `DocumentationAgent` additionally receives `mcp_executor`/`mcp_registry`/`mcp_tool_identities`.
10. `WorkflowNodes` (wraps each agent plus materialization/testing/retry bookkeeping) and `WorkflowBuilder`, which compiles the LangGraph `StateGraph`.
11. `RunService` (JSON run persistence) and `CheckpointService` (SQLite checkpointing) — constructed last since they're per-run, not per-graph.
12. An optional PostgreSQL engine/session factory (`create_db_engine()` — returns `None` if `DATABASE_URL` is unset or unreachable, never raises), a `DatabaseSyncService` subscribed to the same `event_dispatcher` from step 8, and an `AuthService`.

A run is executed via `Application.start_run(request)` / `resume_run(run_id)`, both of which call the private `_execute()`: it builds a fresh, checkpointed, event-and-trace-wrapped graph for that specific `run_id` (`graph_for_run`), invokes it synchronously (`graph.invoke`, never `ainvoke`), saves the resulting state, and emits the terminal `WorkflowEvent`. Both the CLI and the API call these same two methods — the API's `POST /runs`/`POST /runs/{id}/resume` endpoints just run them on a background thread instead of the request thread, since a full workflow run can take minutes.

The API layer (`backend/api/app.py`'s `create_app()`) does not construct its own `Application` differently — its ASGI `lifespan` builds exactly one `Application()` at server startup (mirroring the CLI building exactly one per invocation) and tears it down (`Application.shutdown()`) at server shutdown, plus owns a `ThreadPoolExecutor` for backgrounding long runs.

---

## Architecture Layers

### 1. CLI Layer (`backend/cli/`)

`agentforge create|resume|status|runs|inspect` — argparse-based, five subcommands, structured exit codes (0 success, 2 invalid argument, 3 run not found, 4 run corrupted, 5 workflow completed but FAILED, 130 interrupted). See [API_Design.md](API_Design.md) for the full command reference. `CLIEventRenderer` subscribes to `EventDispatcher` and prints one line per `WorkflowEvent` as the workflow runs. This remains the original, fully independent interface — nothing about it changed when the API layer was added.

### 2. Orchestration Layer (`backend/graph/`)

LangGraph `StateGraph[WorkflowState]`. Nodes are a thin wrapper (`WorkflowNodes`) around each agent's `run()`, plus the parts that are deliberately *not* delegated to the LLM: `MaterializationService` writes generated files to disk after Developer, `TestingService` runs the real test command after Tester, and retry-count/repair-trigger bookkeeping happens directly in `WorkflowNodes.tester`/`.reviewer`. Conditional routing (`backend/graph/router.py`) sends a failed Tester run to Debugger (bounded by `MAX_TEST_RETRIES`) and a failed Reviewer run back to Developer (bounded by `MAX_REVIEW_RETRIES`); exceeding either limit ends the graph with `workflow_status = FAILED`. See [Agent_Design.md](Agent_Design.md) for the full routing diagram.

### 3. Agent Layer (`backend/agents/`)

Eight agents, one per pipeline stage (Analysis, Planner, Architect, Developer, Tester, Debugger, Reviewer, Documentation), sharing one `BaseAgent.run()` template method: build context → invoke LLM (optionally with a bounded MCP tool-calling loop) → validate structured output → update state → mark success/failure on `ExecutionState`. See [Agent_Design.md](Agent_Design.md).

### 4. Shared State Layer (`backend/state/`)

`WorkflowState` is the single object LangGraph threads through every node and the only thing ever checkpointed. It composes eleven typed Pydantic sub-states (conversation, project, planning, architecture, implementation, testing, debug, review, documentation, knowledge, execution). See [State_Management.md](State_Management.md).

### 5. Context & Knowledge Layer (`backend/services/context_manager.py`, `knowledge_manager.py`)

`ContextManager` is the single place that assembles each agent's prompt context: per-agent section selection, relevant-file filtering during repairs, MCP tool documentation, a token budget (via `tiktoken`) enforced by dropping low-priority sections and truncating as a last resort. `KnowledgeManager` is a stateless, deduplicating store of durable project facts (architecture decisions, completed milestones, coding-standard recommendations, known test limitations) recorded by four agents/nodes and surfaced back to five of them through `ContextManager`.

### 6. Tool Integration Layer

Two independent tool systems, deliberately not unified into one class hierarchy:

* **Internal tools** (`backend/tools/`) — synchronous, workspace-sandboxed Python classes (`FilesystemTool`, `TerminalTool`, `GitTool`, `SearchTool`) invoked directly by `MaterializationService`/`TestingService`, never by an LLM.
* **MCP tools** (`backend/mcp/`) — external tools discovered from configured MCP servers via a real FastMCP client, exposed to the LLM via `bind_tools`, executed through a permission-gated `MCPToolExecutor`. See [MCP_Integration.md](MCP_Integration.md).

### 7. AI Model Layer (`backend/llms/`)

`ModelRegistry` loads `backend/llms/config/models.yaml` (one entry per agent role: provider, model name, temperature, max_tokens) and hands off to `ModelFactory`, which dispatches to a per-provider adapter (`backend/llms/providers/{anthropic,cerebras,google,groq,mistral,openrouter,perplexity,zai}.py`, 8 total). Analysis currently uses Perplexity (`sonar-pro`); the other seven roles use Mistral (`mistral-medium-latest`/`mistral-small-latest`); the remaining providers exist and are wired but unused by default. `LLMService.invoke()` builds the system/human messages, optionally binds MCP tool schemas, and is the single point tracing is attached to.

### 8. Observability Layer (`backend/services/tracing_service.py`)

`TracingService` wraps `langsmith.run_helpers.trace` in one reusable context manager, injected into `LLMService`, every internal tool, `MCPToolExecutor`, and the graph builder's node wrapper. It produces one workflow-root span with nested agent/LLM/tool/MCP-call spans per execution. Fully optional: missing credentials or a disabled tracing service degrade silently to normal execution with no LangSmith calls. See the trace hierarchy in [Agent_Design.md](Agent_Design.md).

### 9. Workflow Persistence Layer

Two on-disk mechanisms per run, both under `.agentforge/runs/<run_id>/`, unchanged since before the API layer existed and still the sole source of truth for a run's actual state:

* `RunService` — atomically-written `metadata.json` and `state.json` (the full `WorkflowState`, human-readable), read by `agentforge status`/`inspect`/`runs` and by the API's `GET /runs/{id}`/`{id}/status` (live, not database-backed).
* `CheckpointService` — a LangGraph `SqliteSaver` (`checkpoints.sqlite`, one file per run), the source of truth `agentforge resume` and `POST /runs/{id}/resume` both replay from.

See [Database_Design.md](Database_Design.md) for the full persistence model.

### 10. API Layer (`backend/api/`)

FastAPI, added in v0.11. Routers: `health` (`/`, `/health`, `/version`), `runs` (create/list/get/status/resume — see [API_Design.md](API_Design.md)), `events` (Server-Sent Events), `projects` (project metadata + materialized file listing/content), `knowledge` (project knowledge retrieval), `auth` (a minimal, not-yet-enforced JWT foundation). A single `register_exception_handlers()` maps every `AgentForgeException` subclass to a consistent `{"error": {...}}` JSON response, reusing the same exception hierarchy the CLI's own error handling (`backend/cli/commands.py`) already maps to exit codes. `POST /runs` and `POST /runs/{id}/resume` never block the request for the workflow's full duration — both submit to a `ThreadPoolExecutor` and return as soon as the run ID (or resume acceptance) is known.

### 11. Metadata Persistence Layer (PostgreSQL, optional)

Added in v0.11, strictly additive. `DatabaseSyncService` subscribes to the same `EventDispatcher` every other observability consumer uses; on significant events it re-reads the current `WorkflowState` via `RunService` (never re-implementing state assembly) and upserts denormalized rows into five tables (`runs`, `workflow_events`, `projects`, `knowledge_entries`, `users`) through a repository layer (`backend/repositories/`). Every operation degrades to a logged no-op if no database is configured or reachable — the same optional-dependency posture as `TracingService`. See [Database_Design.md](Database_Design.md).

---

## Request Lifecycle

1. User runs `agentforge create "<request>"`.
2. `RunService.create_run()` allocates a run ID and directory, writes an initial empty `WorkflowState`.
3. `Application._execute()` builds a checkpointed graph for that run ID and calls `graph.invoke()`.
4. Analysis → Planner → Architect run once each, updating their own state section.
5. Developer generates code; `MaterializationService` writes it to `workspace/<run_id>/`.
6. A cheap deterministic StaticValidation pass (syntax/local-import/route checks) runs before Tester and shares its retry budget; Tester proposes a test command and `TestingService` actually runs it. Either failure routes to Debugger → Developer (repair), bounded by `MAX_TEST_RETRIES`. (This step list predates v1.6 — see [Agent_Design.md](Agent_Design.md#workflow-routing) for the current, authoritative routing diagram.)
7. Reviewer evaluates the implementation. Failure also routes through Debugger → Developer (repair, v1.6.x), bounded by `MAX_REVIEW_RETRIES`.
8. Documentation generates project docs, optionally calling any authorized MCP tools.
9. `RunService.save_state()` persists the final state; `WORKFLOW_COMPLETED`/`WORKFLOW_FAILED` is emitted; the CLI prints run ID and status.
10. If interrupted (Ctrl-C, crash, process restart) at any point, `agentforge resume <run_id>` replays from the last LangGraph checkpoint in a brand-new process — completed nodes are not re-run.

Triggering the same lifecycle via the API instead (`POST /api/v1/runs`) differs only in steps 3 and 9: the request handler submits `Application.start_run()` to a background thread and returns `202 Accepted` with the run ID as soon as `WORKFLOW_STARTED` fires (step 2), rather than waiting for the whole workflow; a client then polls `GET /runs/{id}/status` or subscribes to `GET /runs/{id}/events` (SSE) to observe steps 4–9 as they happen. `DatabaseSyncService` mirrors each `WorkflowEvent` into PostgreSQL alongside step 9's file write, if a database is configured.

---

## Design Principles

* Single responsibility per agent; the LLM only ever produces structured output validated against a Pydantic schema.
* `WorkflowState` as the single source of truth and the only object ever checkpointed — no MCP client, connection, or other runtime object is ever persisted.
* Provider-agnostic model integration: swapping a role's provider/model is a `models.yaml` change, not a code change.
* External capabilities only through MCP; internal tools stay Python-orchestrated and workspace-sandboxed.
* Real execution, never simulated: `TestingService` actually runs the test command; `TesterAgent` only proposes it.
* Retry/repair loops are bounded and driven by real evidence (test/review failures), never by LLM self-assessment.
* Observability (LangSmith tracing, structured `WorkflowEvent`s) is additive and fully optional; nothing in the workflow depends on it being enabled.
* The PostgreSQL metadata layer is equally optional: a missing or unreachable database degrades every dependent operation to a logged no-op, never an exception that could break workflow execution or the CLI.
* The CLI and the API are two independent entry points sharing one composition root and zero duplicated business logic; the API never reimplements what `Application`/`RunService`/`EventDispatcher` already do.
* Every new optional dependency (MCP kwargs, context/knowledge managers, tracing service, the database layer) was added as an optional constructor parameter or attribute with a fully backward-compatible default — no existing agent or service signature was broken across the v0.9–v0.11 batches.

---

## Deployment

The backend runs as a Docker image (also deployable to FastAPI Cloud, its current production host); the frontend deploys separately to Vercel. See [Deployment.md](Deployment.md) for the full build/hosting/CORS setup — this document covers system composition, not infrastructure.

---

## Technology Stack Summary

| Layer                | Technology                                                          |
| --------------------- | -------------------------------------------------------------------- |
| Interface              | CLI (`argparse`), FastAPI/SSE (`uvicorn`), and a Next.js frontend    |
| Orchestration          | LangGraph (`StateGraph`, synchronous `graph.invoke`)                |
| Agent framework        | LangChain / `langchain-core`                                        |
| LLM providers          | Mistral + Perplexity (in use), plus Anthropic, Cerebras, Google, Groq, OpenRouter, Z.AI adapters |
| Tool integration       | Internal `BaseTool` subclasses + MCP via FastMCP (stdio/HTTP)        |
| Observability          | LangSmith (optional, degrades to no-op)                              |
| Run persistence        | Plain JSON files (`RunService`), atomic writes                       |
| Checkpointing          | LangGraph `SqliteSaver`, one SQLite DB per run                       |
| Metadata persistence   | PostgreSQL via SQLAlchemy 2.0 + psycopg3, Alembic migrations (optional) |
| Auth                   | JWT (`pyjwt`) + `bcrypt`, enforced on every resource route (v1.1)     |
| Generated output       | Filesystem (`workspace/<run_id>/`)                                    |
| Validation             | Pydantic v2 throughout `backend/state/` and `backend/api/schemas/`   |

**Declared but still unused** (present in `requirements.txt`, not wired into any code path): `redis`. Reflects the original SaaS-platform ambition described in [Project_Vision.md](Project_Vision.md) and [Development_Roadmap.md](Development_Roadmap.md); `fastapi`/`uvicorn`/`sqlalchemy`/`alembic`/`psycopg` moved from this list to genuinely in-use as of v0.11.