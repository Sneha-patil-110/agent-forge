# MCP Integration

## Overview

AgentForge connects to external tool servers via the [Model Context Protocol](https://modelcontextprotocol.io/) using a real [FastMCP](https://github.com/jlowin/fastmcp) client — `stdio` and `HTTP` transports, both genuine FastMCP transport classes, not a custom protocol implementation. This is entirely separate from AgentForge's four internal tools (Filesystem, Terminal, Git, Search — see [System_Architecture.md](System_Architecture.md#6-tool-integration-layer)), which remain synchronous, workspace-sandboxed Python classes invoked directly by application code, never by an LLM.

Only the **Documentation agent** currently has MCP tool access. The shipped configuration enables one demo server (`local-tools`, below) purely so the MCP management page/CLI have genuine data to show — it is granted to **no** agent, so MCP remains functionally inert for actual generation regardless: every agent, and Documentation itself, behaves exactly as if MCP didn't exist unless a server is both enabled *and* explicitly granted in `MCPPermissionPolicy`.

---

## Why Only Documentation

Per agent, MCP tool categories are granted like this:

| Agent | Allowed MCP tools |
|---|---|
| Analysis, Planner, Architect, Developer, Tester, Debugger, Reviewer | none |
| Documentation | `documentation.*` (any tool from a server literally named `documentation`) |

Documentation was chosen because its output isn't routing- or retry-critical (unlike Tester/Reviewer, whose real-execution/repair authority stays Python-only — see [Agent_Design.md](Agent_Design.md)), and its single-shot JSON-output contract made it the cleanest place to prove a bounded tool-calling loop without touching retry/repair semantics anywhere else.

---

## Configuration

`backend/mcp/config.py` — `MCPServerConfig`:

```python
class MCPServerConfig(BaseModel):
    name: str
    display_name: str | None = None   # v1.4: management-surface label; falls back to name
    description: str | None = None    # v1.4: management-surface description
    enabled: bool = False
    transport: MCPTransport          # "stdio" | "http"
    command: str | None = None
    args: list[str] = []
    env: dict[str, str] = {}          # {local_var_name: ENV_VAR_NAME_TO_READ}
    url: str | None = None
    auth: MCPServerAuth = MCPServerAuth()   # v1.4: remote authentication, see below
    connection_timeout: float = 10.0
    tool_timeout: float = 30.0
```

Loaded from `backend/mcp/config/mcp_servers.yaml` (`extra="forbid"`; a model validator rejects `stdio` without `command`, `http` without `url`, or `auth.type != "none"` on `stdio` — auth is HTTP-only). A server with `enabled: false` (or entirely absent) means `MCPClientManager.get_client()` raises `MCPServerNotFoundError` before any connection is attempted.

**Shipped demo server**: `local-tools` (`backend/mcp/example_servers/local_tools.py`) — a tiny `stdio` FastMCP server with three trivial tools (`current_time`, `echo`, `word_count`), enabled by default so the MCP management page (`/mcp`) and `agentforge mcp` CLI have real, connectable data out of the box instead of an empty state. It exists purely to demonstrate the management surface — `MCPPermissionPolicy` grants it to no agent, so it adds zero actual capability. `test_shipped_config_includes_the_local_tools_demo_server` (`tests/test_mcp_application_wiring.py`) locks in both halves of this: the server is enabled by default, and it's granted to nobody.

**Full shipped roster** (`backend/mcp/config/mcp_servers.yaml`, all `enabled: true`, none granted to any agent except Documentation's `documentation.*` wildcard — enabling a server here only makes it connectable/inspectable via the management surface, not usable by any agent):

| Server | Transport | Command | Notes |
|---|---|---|---|
| `local-tools` | stdio | `${PYTHON} -m backend.mcp.example_servers.local_tools` | Demo server, see above |
| `github` | http | — | GitHub's hosted Copilot MCP endpoint |
| `context7` | http | — | Framework/library documentation |
| `exa` | http | — | Web research |
| `filesystem` | stdio | `${PYTHON} -m backend.mcp.example_servers.filesystem` | First-party Python, read-only, sandboxed to `WORKSPACE_ROOT` |
| `sequential-thinking` | stdio | `${PYTHON} -m backend.mcp.example_servers.sequential_thinking` | First-party Python, matches the official `sequentialthinking` tool schema |
| `postgres` | stdio | `${PYTHON} -m backend.mcp.example_servers.postgres` | First-party Python, read-only (SELECT/WITH/EXPLAIN/SHOW only) |
| `playwright` | stdio | `npx -y @playwright/mcp@latest` | Node-dependent — see "Node.js Dependency" below |

### Node.js Dependency (v1.7)

`filesystem`, `sequential-thinking`, and `postgres` were originally configured as `npx`-launched Node packages (`@modelcontextprotocol/server-filesystem`, `@modelcontextprotocol/server-sequential-thinking`, `mcp-postgres-server`), matching `playwright`'s pattern below. This worked in local development and in the project's own Docker image (which installs Node.js — see [Deployment.md](Deployment.md)), but **FastAPI Cloud does not use that Docker image**: it builds and runs the source directly via its own Python-only `uv` pipeline, with no Node.js in the runtime at all. All four `npx`-based servers failed identically in production with `[Errno 2] No such file or directory` (the `npx` executable itself doesn't exist there) — confirmed directly via the live health-check API's `error` field, not assumed.

Three of the four have no real dependency on being a Node package specifically, so they were reimplemented/replaced to remove the Node dependency entirely:

* **`filesystem`** — a first-party FastMCP server (`backend/mcp/example_servers/filesystem.py`) implementing the same 8 read-only tools (`read_text_file`, `read_multiple_files`, `list_directory`, `list_directory_with_sizes`, `directory_tree`, `search_files`, `get_file_info`, `list_allowed_directories`), matching the official server's tool names/schemas exactly, sandboxed to `WORKSPACE_ROOT` via a `resolve()` + `relative_to()` traversal check. The write/edit tools the npm package exposed were deliberately not reimplemented — writes always go through `MaterializationService`, never this server, so there was nothing to grant regardless.
* **`sequential-thinking`** — a first-party FastMCP server (`backend/mcp/example_servers/sequential_thinking.py`) implementing the single `sequentialthinking` tool with an identical input schema, matching the official server's response shape (`thoughtNumber`/`totalThoughts`/`nextThoughtNeeded`/`branches`/`thoughtHistoryLength`).
* **`postgres`** — a first-party FastMCP server (`backend/mcp/example_servers/postgres.py`) using SQLAlchemy's `inspect()` API directly (already a dependency, no new package) for `list_schemas`/`list_tables`/`describe_table`, plus a guarded `execute_query` that rejects anything not starting with `SELECT`/`WITH`/`EXPLAIN`/`SHOW` and runs inside a transaction that's always rolled back regardless. Reads `DATABASE_URL` directly and passes it straight to `create_engine()`, so SQLAlchemy's own `postgresql+psycopg://` dialect handling applies unchanged — no connection-string normalization needed.

  **This wasn't the first attempt.** The first fix switched to [`postgres-mcp`](https://github.com/crystaldba/postgres-mcp) (a real, actively-maintained pip package) — verified working against a local database, full test suite green, and then it broke the *entire* production build: `postgres-mcp`'s published versions all require Python ≥3.12/3.13, while this project targets 3.11, and local testing happened to run on a newer interpreter, masking the incompatibility until the actual FastAPI Cloud build failed. A second candidate (`postgresql-mcp`) supported Python 3.11 but its documented interface (env vars, module name) couldn't be independently verified against real source before another deploy cycle would have been needed. Given a third-party package had already broken production once, the first-party rewrite was the safer choice — full control, zero version/interface risk, and it was already the proven pattern for `filesystem` and `sequential-thinking` above.

**`playwright` remains Node-dependent and is not fixed.** Real browser automation needs actual Chromium/Firefox binaries plus a substantial set of Linux shared libraries (`libnss3`, `libatk-bridge2.0-0`, `libgbm`, etc.) that neither `pip` nor `npm` install on their own — normally an `apt-get install`/Dockerfile concern. FastAPI Cloud exposes no Dockerfile or system-package installation surface, so this is very likely unfixable in that specific environment regardless of language runtime, not just a missing-Node problem. This is disclosed here rather than papered over; see [Future_Improvements.md](Future_Improvements.md).

### Stdio Failure Diagnostics (v1.7)

`MCPClientManager` now passes a per-server `log_file` (`logs/mcp/<server>.stderr.log`) to FastMCP's `StdioTransport`, truncated before each connection attempt. On a connection failure, the last 4000 characters of that file are appended to the raised `MCPConnectionError` (and therefore to `MCPHealthResult.error`, already exposed via the health-check/reconnect API and the `/mcp` dashboard). Previously a health check only ever showed a bare `"unreachable"` status with no indication of *why* — this is how the `[Errno 2] No such file or directory` root cause above was actually confirmed, directly against the live deployment, rather than guessed at.

Enabling a real server for the first time surfaced a real, previously-dormant bug: `Application.__init__` (via `_discover_mcp_tools()`) called `asyncio.run()` directly, which works when `Application()` is constructed synchronously (the CLI) but raises `RuntimeError: asyncio.run() cannot be called from a running event loop` when constructed from FastAPI's async `lifespan` (uvicorn already has its own loop running on that thread) — a path that had never been exercised before since no server was ever enabled by default until now. Fixed with a small `_run_async()` helper (`backend/core/app.py`) that detects an already-running loop and, if present, delegates to a dedicated worker thread running its own fresh `asyncio.run()`; used by both `_discover_mcp_tools()` and `shutdown()`. Covered by `tests/test_application_run_async.py`, which reproduces the exact failing scenario.

**Secrets are never stored in this file.** The `env` field maps a local variable name to the *name* of an environment variable to read — `resolved_env()` reads the actual value from `os.environ` only at connect time, so a committed `mcp_servers.yaml` can never contain a secret value. `auth.credential_env_var` (v1.4) follows the identical pattern for remote HTTP authentication — see "Remote Authentication (v1.4)" below.

### Remote Authentication (v1.4)

```python
class MCPAuthType(str, Enum):
    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    CUSTOM_HEADER = "custom_header"
    OAUTH = "oauth"    # declared, not yet wired to a transport
    MTLS = "mtls"      # declared, not yet wired to a transport

class MCPServerAuth(BaseModel):
    type: MCPAuthType = MCPAuthType.NONE
    credential_env_var: str | None = None   # name of the env var holding the secret -- never the value
    header_name: str | None = None          # header name for api_key/custom_header
```

`MCPServerConfig.resolved_auth_headers()` builds the actual HTTP headers at transport-construction time — `{"Authorization": f"Bearer {value}"}` for `bearer`, `{header_name or "X-API-Key": value}` for `api_key`, `{header_name or "Authorization": value}` for `custom_header` — and `_build_transport()` (`backend/mcp/client_manager.py`) passes them to FastMCP's `StreamableHttpTransport(url=..., headers=...)`. An unset env var resolves to an empty header dict (a misconfigured credential surfaces as a connection failure at connect time, not a startup crash). `oauth`/`mtls` are real enum values — a management UI or config file can already declare a server as using one — but `resolved_auth_headers()` returns nothing for them; they're forward-declared, not implemented.

---

## Architecture

```text
Application.__init__
    │
    ├── MCPClientManager(load_mcp_server_configs())
    ├── MCPToolRegistry()
    ├── _discover_mcp_tools()  ── for each enabled server: discover_tools() → register_server_tools()
    │                              (a server that fails to connect is skipped, not fatal to startup)
    ├── MCPPermissionPolicy({DOCUMENTATION: {"documentation.*"}})
    └── MCPToolExecutor(client_manager, registry, permission_policy, event_dispatcher, tracing_service)
            │
            └── passed only to DocumentationAgent's mcp_executor/mcp_registry/mcp_tool_identities
                (the other 7 agents are constructed with none of these — mcp_executor=None)
```

### Client Lifecycle (`backend/mcp/client_manager.py`)

`MCPClientManager` creates FastMCP `Client` instances lazily, one per server, on first use; `Application` owns exactly one manager for its whole lifetime (shared across CLI and API — see [System_Architecture.md](System_Architecture.md)). Connections are reused within one event loop; `Application.shutdown()` calls `close_all()`. A connection failure is caught and re-raised as `MCPConnectionError`.

**Known limitation**: a connection does not reliably survive being reused across separate `asyncio.run()` calls (each creates a new event loop). `MCPToolExecutor.execute()` calls `asyncio.run()` once per tool call, so a connection may be transparently re-established per call rather than truly persisted. Correctness is unaffected; this is a documented efficiency trade-off, not a defect — see [Future_Improvements.md](Future_Improvements.md).

### Tool Discovery (`backend/mcp/discovery.py`)

`discover_tools(client_manager, server_name)` calls the real `client.list_tools()` and wraps each result in a small typed `DiscoveredTool` (`identity`, `server_name`, `tool_name`, `description`, `input_schema`) — never a raw `mcp.types.Tool` passthrough. Naming convention: `<server_name>.<tool_name>` (e.g. `documentation.search_docs`).

### Registry (`backend/mcp/registry.py`)

`MCPToolRegistry` is a separate, small class from the internal `ToolRegistry` — different execution model (async-backed, server-scoped, no filesystem sandboxing concept), deliberately not forced into one shared hierarchy. Re-registering the same identity from the same server is a harmless no-op (idempotent re-discovery); a different server claiming an already-registered identity raises `MCPDuplicateToolError`.

### Permissions (`backend/mcp/permissions.py`)

`MCPPermissionPolicy.is_authorized()` is **deny-by-default**: an agent with no entry in the policy is denied everything, unconditionally. Wildcard matching (`documentation.*`) is supported. Checked unconditionally inside `MCPToolExecutor.execute()` on every single call — never trusted from an agent's own locally-declared `mcp_tool_identities` list, which is only a UX/context-narrowing hint.

### Execution (`backend/mcp/executor.py`)

```text
MCPToolExecutor.execute(agent, tool_identity, arguments)
    → MCPToolRegistry.get(tool_identity)        (MCPToolNotFoundError if unknown)
    → MCPPermissionPolicy.is_authorized(...)     (MCPPermissionDeniedError if not)
    → asyncio.run(self._call(tool, arguments))
        → MCPClientManager.get_client(server_name)
        → client.call_tool(tool_name, arguments, timeout=...)   (real FastMCP call)
    → _bound_result(raw_result)                  (truncate + serialize safely)
```

Argument validation is **not duplicated** — FastMCP validates arguments against the tool's own discovered schema before the tool function ever executes; AgentForge only catches and maps (`ToolError`/`FastMCPError` → `MCPToolExecutionError`). Results are capped at `MAX_MCP_RESULT_CHARS` (8000, matching `TestingService`'s own truncation convention exactly) with a `"... [{N} characters truncated]"` marker.

### Agent Integration (`backend/agents/base_agent.py`)

`BaseAgent._invoke_with_tools()` is a bounded loop (`MAX_MCP_TOOL_ROUNDS = 3`): binds tool schemas via `LLMService.invoke(..., tools=...)`, feeds tool results back as `ToolMessage`s, and falls back to one final tools-less call if the round budget is exhausted without the LLM returning a final answer. Shared by any future agent that opts in the same way — nothing about it is Documentation-specific except which agent currently has `mcp_tool_identities` populated.

---

## Observability

Every MCP tool call is both traced (a `mcp:<tool_identity>` LangSmith span tagged with `mcp_server`/`mcp_tool`/`agent`, when tracing is enabled — see [Agent_Design.md](Agent_Design.md#observability)) and emits structured `WorkflowEvent`s:

| Event | Emitted | Metadata |
|---|---|---|
| `MCP_TOOL_CALL_STARTED` | before the call | `{"tool": identity}` |
| `MCP_TOOL_CALL_COMPLETED` | after success | `{"tool": identity}` |
| `MCP_TOOL_CALL_FAILED` | on any exception | `{"tool": identity}`, `message=str(error)` |

Only the tool identity string is ever included — never arguments or results. Since v0.11 these events are additionally visible over the API's SSE stream (`GET /api/v1/runs/{id}/events`) and optionally mirrored into PostgreSQL by `DatabaseSyncService` — see [API_Design.md](API_Design.md) and [Database_Design.md](Database_Design.md). No new instrumentation was added for this; it's the same `EventDispatcher` every other observer already subscribes to.

---

## Persistence and Resume Safety

No MCP object — `MCPClientManager`, any FastMCP `Client`, `MCPToolExecutor` — is ever a field on `WorkflowState`, checked directly by walking every field reachable from the model. A resumed run (`agentforge resume` or `POST /runs/{id}/resume`, potentially in a brand-new process) builds a completely fresh MCP subsystem via a new `Application()`; a Documentation agent that resumes mid-tool-use makes a genuine new MCP call against that fresh infrastructure, proven directly by an end-to-end test that interrupts and resumes a run with a real MCP tool call on both sides. See [State_Management.md](State_Management.md#checkpointing-and-resume).

---

## Security Posture

* Unauthorized tool calls are rejected by the permission policy, checked on every single call, never cached or trusted from an agent's own claim.
* Tool name collisions across servers are rejected (`MCPDuplicateToolError`); same-server re-registration is a safe no-op.
* Results are size-bounded (8000 chars) before ever re-entering an LLM context via `ToolMessage`.
* Timeouts (`connection_timeout`, `tool_timeout`, per-server) are enforced by FastMCP itself and mapped to `MCPTimeoutError`.
* Secrets never appear in a committed config file, an event, a trace span, or a log line — only the environment-variable *name* is ever stored; the value is read once, at connect time, directly into the subprocess/HTTP client.
* **What is explicitly not sandboxed**: an enabled, authorized MCP server is trusted to the extent AgentForge's own permission policy and result-bounding provide. There is no OS-level sandboxing (no container, no seccomp, no restricted filesystem namespace) around an MCP server process — AgentForge's guarantees are about *which agent may request which tool*, not about containing what a legitimately-authorized server's own process can do on the host.

---

## Current Limitations

* Transports: `stdio` and `HTTP` only (no SSE transport, no in-process FastMCP transport for production use).
* Agent access: Documentation only.
* Remote MCP tool execution has no UI — the frontend's `/mcp` page and `agentforge mcp` CLI group (both v1.4) are inspection/administration only, matching the backend's own scope; there is no way to manually invoke a tool outside of a Documentation agent actually calling it.
* Per-call reconnect overhead (see Client Lifecycle above) — acceptable at current call volumes, a candidate optimization if that changes.
* No automatic health polling — a server's cached health status is only ever refreshed by an explicit `POST /servers/{name}/health-check`, `POST /refresh`, or the CLI's `mcp health`/`mcp test`, never on a timer.
* `oauth`/`mtls` auth types are declared in `MCPAuthType` (v1.4) but have no transport wiring yet — a server configured with either is accepted at config-validation time but its `resolved_auth_headers()` won't produce anything meaningful.
* **`playwright` cannot connect in production (v1.7).** It's the one remaining `npx`-launched server (see "Node.js Dependency" above) and, unlike the other three, can't simply be reimplemented in Python — real browser automation needs Chromium/Firefox binaries plus Linux shared libraries that FastAPI Cloud's environment has no exposed way to install. Works locally and in the project's own Docker image, where Node and a full apt-based install are both available.

**Resolved as of v1.4** (kept here only so this section doesn't silently drift stale again): remote MCP servers can now authenticate (`MCPServerConfig.auth`, `api_key`/`bearer`/`custom_header` — see "Remote Authentication" above); `agentforge mcp list|inspect|tools|test|health|refresh` and the equivalent `/api/v1/mcp/*` REST endpoints both exist — see [API_Design.md](API_Design.md#mcp-management-v14) and the CLI section there.

See [Future_Improvements.md](Future_Improvements.md) for what would motivate lifting any of the still-open ones.