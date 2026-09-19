# Agent Design

## Overview

AgentForge runs eight agents in a fixed LangGraph pipeline, defined by `WorkflowNode` (`backend/graph/workflow.py`): Analysis → Planner → Architect → Developer → Tester → (Debugger) → Reviewer → Documentation. Every agent is a subclass of `BaseAgent` (`backend/agents/base_agent.py`), which implements one shared execution template; each concrete agent only supplies its `name`, `prompt_file`, `model_role`, `build_context()`, `validate()`, and `update_state()`.

This pipeline runs identically regardless of which entry point triggered it — the CLI (`agentforge create`) or the FastAPI API (`POST /api/v1/runs`, added in v0.11); both call the same `Application.start_run()`/`resume_run()`. See [System_Architecture.md](System_Architecture.md) for how the two entry points share one composition root.

Two things are true of every agent and are worth stating up front because they shape the whole design:

* **The LLM never runs anything for real.** Developer's code isn't written to disk by the LLM — `MaterializationService` does that. Tester's proposed command isn't executed by the LLM — `TestingService` actually runs it. This keeps real evidence (file writes, test exit codes) authoritative over LLM self-report.
* **Retry/repair loops are driven by that real evidence**, not by an agent claiming success. `WorkflowNodes.tester()`/`.reviewer()` increment retry counters and set `ExecutionState.last_repair_trigger` directly — never inside an agent.

---

## `BaseAgent.run()` — the shared execution template

```text
_mark_running(state)                          # workflow_status=RUNNING, current_agent=self
      │
      ▼
prompt = load_prompt()                        # PromptService, cached per file
      │
      ▼
context = build_context(state)                # delegates to ContextManager (per-agent builder)
      │
      ▼
has MCP tools? ──yes──▶ _invoke_with_tools()   # bounded tool-calling loop (Documentation only)
      │no
      ▼
response = llm_service.invoke(...)            # single LLM call, no tools
      │
      ▼
validated_output = validate(response)          # parse + Pydantic-validate structured JSON
      │
      ▼
state = update_state(state, validated_output)  # agent writes only its own state section
      │
      ▼
_mark_success(state)                          # Documentation additionally marks COMPLETED
```

Any exception is caught, `_mark_failure()` sets `workflow_status=FAILED` with the error message, and the exception is re-raised (wrapped as `AgentExecutionError` if it wasn't already an `AgentForgeException`) — the graph run fails loudly rather than silently continuing with bad state.

---

## The Eight Agents

| # | Agent | `name` | Prompt | Model role | Output state | Tools |
|---|-------|--------|--------|------------|---------------|-------|
| 1 | `AnalysisAgent` | `analysis` | `analysis.md` | `analysis` | `ProjectState` | none |
| 2 | `PlannerAgent` | `planner` | `planner.md` | `planner` | `PlanningState` | none |
| 3 | `ArchitectAgent` | `architect` | `architect.md` | `architect` | `ArchitectureState` | none |
| 4 | `DeveloperAgent` | `developer` | `developer.md` | `developer` | `ImplementationState` | none (LLM); `MaterializationService` writes files afterward |
| 5 | `TesterAgent` | `tester` | `tester.md` | `tester` | `TestingState` (command only) | none (LLM); `TestingService` actually executes afterward |
| 6 | `DebuggerAgent` | `debugger` | `debugger.md` | `debugger` | `DebugState` | none — never modifies files or runs commands |
| 7 | `ReviewerAgent` | `reviewer` | `reviewer.md` | `reviewer` | `ReviewState` | none |
| 8 | `DocumentationAgent` | `documentation` | `documentation.md` | `documentation` | `DocumentationState` | any MCP tool matching `documentation.*` (if configured) |

Analysis currently resolves to Perplexity `sonar-pro`; the other seven roles resolve to Mistral (`mistral-medium-latest` for Planner/Architect/Developer/Reviewer/Debugger/Tester, `mistral-small-latest` for Documentation) in `backend/llms/config/models.yaml`, with per-role `temperature`/`max_tokens` tuning (Reviewer/Debugger/Tester/Developer use `temperature=0.0` for consistency; Developer gets the largest `max_tokens=24576`). Changing a role's model is a YAML edit, not a code change — `ModelRegistry`/`ModelFactory` dispatch to whichever of the 8 registered provider adapters (Anthropic, Cerebras, Google, Groq, Mistral, OpenRouter, Perplexity, Z.AI) is named.

### 1. Analysis Agent
Interprets the raw user request into structured `ProjectState`: project name/description/objective, requirements, inferred tech stack (`backend`/`frontend`/`database`/`deployment`), target audience, and `pending_clarifications` for anything ambiguous.

### 2. Planner Agent
Produces `PlanningState`: an ordered `tasks` list (with dependencies and milestone linkage, cycle- and uniqueness-validated by a Pydantic model validator), `milestones`, `risks`, and an `implementation_strategy` summary.

### 3. Architect Agent
Produces `ArchitectureState`: `system_design` (layers + communication flow), `components`, `api_design`, `database_design`, `design_patterns`, and `architecture_decisions` (each with a `status` — proposed/accepted/rejected/deprecated/superseded). Every `ACCEPTED` decision is recorded into shared project knowledge (see below), deduplicated by decision ID so re-running never double-records.

### 4. Developer Agent
Produces `ImplementationState.generated_code` (full file contents, not diffs). `written_files`/`file_write_errors` are filled in afterward by `MaterializationService`, never by the agent itself — this is enforced by the state model's own docstring convention. On a repair pass (see below), the agent's context is narrowed to only the files implicated by the failure. `update_state()` diffs `completed_tasks` before/after and records only genuinely new completions as knowledge.

### 5. Tester Agent
Selects a test command for the generated implementation — it never runs it. `WorkflowNodes.tester()` calls `TestingService.execute()` with that command, which performs a real subprocess run (bounded by `TEST_EXECUTION_TIMEOUT`, output capped at `MAX_TEST_OUTPUT_CHARS`) and overwrites `state.testing` with the real result: exit code, stdout/stderr, parsed pass/fail counts, individual `TestFailure` records. Only after this real run does retry logic engage.

### 6. Debugger Agent
Entered when a real test run fails and retries remain, **or** (as of v1.6.x) when Reviewer requests changes and retries remain — either way, Developer never sees raw, unanalyzed failure/feedback data; Debugger's job is to turn it into an actionable brief first. Analyzes `state.testing`'s real failure evidence (test-triggered) or `state.review`'s real feedback (review-triggered) and produces `DebugState`: `root_cause`, `failure_category`, `affected_files`, `repair_instructions`, per-file `suggested_changes`, and a `confidence` score — the same output shape either way. Never modifies files or executes commands, and never asserts that a repair (or a review fix) succeeded — only a subsequent real test run and review pass can confirm that. Which trigger applies is read from `RepairTrigger` (`TEST_FAILURE`/`STATIC_VALIDATION_FAILURE` vs. `REVIEW_FEEDBACK`), set by whichever upstream node (`static_validation()`, `tester()`'s router, or `reviewer()`) routed here.

### 7. Reviewer Agent
Evaluates the implementation and produces `ReviewState`: `passed`, a `score` (0–10), `issues` (each with a `severity`), `strengths`, `recommendations`. A Pydantic model validator enforces the actual approval rule programmatically: `passed` cannot be `True` if any `CRITICAL` or `HIGH` severity issue exists, regardless of what the LLM claims. Each recommendation is recorded into shared knowledge, deduplicated by content so repeated review cycles don't pile up duplicates.

### 8. Documentation Agent
The only agent with MCP tool access. Produces `DocumentationState`: `generated_docs` (title/path/content, capped at 6 files), a summary, and `pending_documentation`. If MCP tools are configured and authorized (`documentation.*`), it runs through `BaseAgent._invoke_with_tools()` — a bounded loop (`MAX_MCP_TOOL_ROUNDS = 3`) that lets the LLM call tools via `bind_tools`, feeds results back as `ToolMessage`s, and falls back to a final tools-less call if the round budget is exhausted. See [MCP_Integration.md](MCP_Integration.md) for the full tool-call architecture. With no MCP servers configured (the shipped default), this agent behaves exactly like the other seven.

As of v1.1, `generated_docs` is materialized to disk by `MaterializationService.materialize_documentation()` (mirroring how the Developer agent's `generated_code` is written, via a shared `_write_files()` helper) and retrievable via `GET /api/v1/runs/{run_id}/repo/documentation` — see [API_Design.md](API_Design.md). `WorkflowNodes.documentation()` calls this immediately after the agent runs, and `graph/builder.py` emits a `DOCUMENTATION_GENERATED` event with the written file count, following the same event-wrapping pattern as the Tester/Reviewer nodes' pass/fail events.

As of v1.2, `WorkflowNodes.documentation()` also captures `state.documentation.written_files` *before* the agent runs and passes it through as `previous_written_files`, the same carry-forward pattern the Developer node already used — so a resumed workflow re-reaching this node, or any regeneration, never loses track of docs a prior attempt wrote just because the current attempt proposed fewer files. `DOCUMENTATION_GENERATED` is also now a `DatabaseSyncService` snapshot event, syncing `generated_docs`' identity/status (not content) into `documentation_files` — see [Database_Design.md](Database_Design.md) and [API_Design.md](API_Design.md)'s "Documentation Persistence" section.

### Static Validation (v1.6) — a ninth graph node, not a ninth LLM agent

`WorkflowNodes.static_validation()` sits between Developer and Tester and is deliberately **not** an `LLMService`-backed agent: it's a cheap, deterministic Python check (`backend/services/static_validation_service.py`) — `ast.parse()` syntax validation, local-import resolution (relative imports and absolute imports under a top-level package the project itself defines; third-party/stdlib imports are intentionally never checked, since this runs inside AgentForge's own interpreter, not the generated project's — checking those would produce false positives on legitimate imports AgentForge itself doesn't happen to have installed), and a narrow "is any FastAPI router ever `include_router`-ed at all" structural check. Motivation: the expense-tracker bug that prompted the v1.6 audit (a missing Pydantic field) was a deterministic, syntactic-adjacent class of error that a full pytest subprocess run is a slow, expensive way to discover.

On failure, it populates `state.testing` with synthetic `TestFailure` entries in the exact shape a real Tester failure would produce, sets `RepairTrigger.STATIC_VALIDATION_FAILURE` (a value `debugger()`/`_build_developer_context` treat identically to `TEST_FAILURE` for context-building purposes — only the label differs, for observability), and shares Tester's `test_retry_count`/`MAX_TEST_RETRIES` budget rather than a separate counter, since this is a faster way to *reach* the same repair loop, not an additional retry allowance. On success it leaves a harmless placeholder in `state.testing` that Tester unconditionally overwrites the moment it runs. Explicitly out of scope: cross-checking Pydantic schemas against SQLAlchemy models, deep relationship/migration validation, and general static analysis (mypy/ruff-in-the-loop) — flagged in [Future_Improvements.md](Future_Improvements.md) as the natural next step once this narrower pass proves out.

#### v1.6.x — Workflow Progress Graph Consistency Fix

Shortly after this node shipped, the frontend's workflow-progress diagram could show `tester` marked complete while `static_validation` (which structurally gates it) had never completed on that run — an impossible state. Root-caused directly against real recorded `workflow_events` for a genuine run, not assumed: the **backend graph, edges, and event emission were all correct** — every real event confirmed `static_validation` genuinely gates `tester` — the bug was entirely in `AgentPipeline`'s `deriveStates()` (frontend), which derived each node's displayed status independently, with no awareness of pipeline order, so a node's stale "completed" mark from an earlier attempt (a prior repair cycle, or — the specific case that surfaced it — a run created before `static_validation` existed) never got invalidated when the workflow legitimately looped back upstream. Fixed by resetting every node from the (re-)started node onward to "pending" on each `agent_started`, so a node can only ever show "completed" if it's the *current* pass's completion. A second, smaller contributing factor: node order was hand-duplicated as a TypeScript constant separate from the backend's own `WorkflowNode` enum, with nothing keeping the two in sync — closed by a new `GET /api/v1/workflow/graph` endpoint (see [API_Design.md](API_Design.md#workflow-graph-v16x)) serving the real compiled graph's node order/edges, which the frontend now fetches instead of maintaining its own copy. See [Frontend_Design.md](Frontend_Design.md) for the full frontend-side writeup.

---

## Workflow Routing

```text
START
  │
  ▼
Analysis → Planner → Architect → Developer ──────────────┐
                                     ▲                    │
                                     │                    ▼
                                     │              StaticValidation
                                     │               passed │ failed
                                     │                      ▼
                                     │                    Tester
                                     │               passed │ failed
                                     │                      ▼
                                     │                  Reviewer
                                     │               passed │ failed
                                     │                      │        │
                                     │                      │        ▼
                                     │                      │    Debugger
                                     │                      │  (any of the three
                                     │                      │   failure branches
                                     └──────────────────────┼── above lands here;
                                        Debugger always      │   retries < the
                                        routes back here     │   relevant limit)
                                                              │
                                                              ▼ retries exhausted
                                                          END (FAILED)
                                     ▼ (Reviewer passed)
                             Documentation
                                   │
                                  END (COMPLETED)
```

All three failure branches (`StaticValidation`/`Tester`/`Reviewer`) route into the *same* `Debugger` node, not three separate analyzers — `Debugger` always routes back to `Developer` afterward (`backend/graph/edges.py`'s one unconditional `(DEBUGGER, DEVELOPER)` edge), regardless of which of the three triggered it. Routing decisions (`backend/graph/router.py`) only ever read state — they never mutate retry counters or `workflow_status`; that bookkeeping lives entirely in `WorkflowNodes.static_validation()`/`.tester()`/`.reviewer()`. `RepairTrigger` (`NONE` / `TEST_FAILURE` / `REVIEW_FEEDBACK` / `STATIC_VALIDATION_FAILURE`) tells `Debugger` which real evidence to analyze (`state.testing` vs. `state.review`) and tells a re-entered `Developer` which of `Debugger`'s briefs is current. `MAX_TEST_RETRIES` and `MAX_REVIEW_RETRIES` are independent counters (both default to 3, `backend/core/constants.py`); `StaticValidation` and `Tester` share the `test_retry_count` counter rather than each getting their own, since both routes into `Debugger` are the same underlying "give Developer another attempt" budget — `Reviewer`'s `review_retry_count` stays separate.

**v1.6.x:** before this, `Reviewer`'s failure branch skipped `Debugger` entirely and hit `Developer` directly with raw, unanalyzed review issues — the only one of the three failure paths that worked this way, an inconsistency rather than a deliberate design choice. `review_router` (`backend/graph/router.py`) now routes a failed review into `Debugger` first, exactly like `static_validation_router`/`tester_router` already did, so `Developer` gets the same kind of analyzed, actionable brief regardless of what triggered the repair. `Debugger`'s prompt (`backend/prompts/debugger.md`) and `_build_debugger_context`/`_build_developer_context` (`backend/services/context_manager.py`) were updated to read whichever real evidence applies (`TestingState` or `ReviewState`) rather than assuming a test failure. `DebuggerAgent.update_state()`'s `attempt_number` now reads `review_retry_count` instead of `test_retry_count` for a review-triggered pass, since that's the counter this analysis is actually bound by.

---

## Context Assembly

No agent hand-rolls its own prompt context. `BaseAgent.build_context()` on every concrete agent delegates to a shared `ContextManager` (`backend/services/context_manager.py`), which:

* Dispatches to a per-agent builder that includes only the `WorkflowState` sections that agent's own prompt (`backend/prompts/<name>.md`, "# Input" section) documents needing.
* During a Developer repair, filters `generated_code` down to files implicated by the failure — `debug.affected_files` / `debug.suggested_changes`, the same source for all three repair triggers as of v1.6.x, since Debugger now analyzes review feedback too, not just test failures — falling back to the full file list if nothing matches, never to an empty section.
* Appends an MCP tool-documentation section for agents with MCP access.
* Appends a "Project Knowledge" section (see below) for five of the eight agents.
* Enforces a token budget (`DEFAULT_CONTEXT_TOKEN_BUDGET = 16000`, counted with `tiktoken`) by dropping the lowest-priority sections first, then truncating the largest remaining required section as a last resort.

---

## Shared Project Knowledge

`KnowledgeManager` (`backend/services/knowledge_manager.py`) is a stateless, deduplicating store layered on top of `WorkflowState.knowledge`, needed because several state sections (`review`, `testing`, `debug`, `implementation`) are wholesale-replaced on every re-invocation — a fact worth keeping ("this was already decided", "this test is a known failure") would otherwise vanish the moment its source section is overwritten.

```text
 Architect  ── record(ARCHITECTURE_DECISION) ──┐
 Developer  ── record(COMPLETED_MILESTONE)  ───┤
 Reviewer   ── record(CODING_STANDARD)      ───┼──▶ state.knowledge.entries
 Tester node ─ record(KNOWN_LIMITATION)     ───┘
                                                        │
                                          KnowledgeManager.get(...)
                                                        │
                                                        ▼
                                 "Project Knowledge" context section for:
                          Planner, Architect, Developer, Reviewer, Documentation
                        (Analysis, Tester, Debugger do not receive this section)
```

Entries are deduplicated by `source_id` when the originating object has a stable ID (e.g. an architecture decision), otherwise by exact content match. `replace()` marks an old entry `SUPERSEDED` rather than deleting it, so history is preserved but `get()` only ever surfaces the current `ACTIVE` fact. Architecture decisions are excluded from the knowledge section specifically for the agents that already see the full "Architecture Information" section, to avoid duplication.

---

## Observability

Every agent invocation, LLM call, tool call, and MCP call opens a LangSmith span (when tracing is enabled) via the shared `TracingService`, nested automatically under one root `workflow` span per run:

```text
workflow
├── analysis
├── planner
├── architect
├── developer
│   └── llm:developer
├── tester
├── debugger                 (only if testing failed)
├── developer_repair          (retry_triggered_by=test_failure, retry_number=1, ...)
├── tester
├── reviewer
├── developer_repair          (retry_triggered_by=review_feedback, ...)
├── tester
├── reviewer
└── documentation
    └── mcp:<tool>            (only if Documentation calls an MCP tool)
```

A Developer repair pass is labeled `developer_repair` with `retry_triggered_by`/`retry_number`/`previous_stage`/`next_stage` metadata, computed read-only from `ExecutionState` — this changes nothing about routing or retry accounting, only how the same execution appears in a trace. Tracing degrades to a complete no-op when disabled or misconfigured; nothing in the workflow depends on it.

Since v0.11, every `WorkflowEvent` emitted alongside this pipeline (`AGENT_STARTED`/`AGENT_COMPLETED`/`TESTING_*`/`REVIEW_*`/etc.) is also optionally mirrored into PostgreSQL by `DatabaseSyncService`, and can be watched live over Server-Sent Events (`GET /api/v1/runs/{id}/events`) — see [API_Design.md](API_Design.md). This is a second, independent observer of the same `EventDispatcher` the CLI's own renderer and LangSmith tracing already use; nothing about agent execution changed to support it.

### Failure classification, per-invocation analytics, and recovery (v1.6)

**Motivation.** Before v1.6, AgentForge had no way to distinguish a transient failure (worth retrying) from a deterministic one (retrying just repeats it) — `LLMService.invoke()` caught every provider exception into one generic `LLMError`, an unused `RateLimitExceededError`/`ProviderUnavailableError`/etc. taxonomy existed in `core/exceptions.py` but was never instantiated, and all retry behavior was silently delegated to the OpenAI-SDK-compatible client's own defaults (`max_retries=2`). A live investigation into a real "keeps failing" report (an LLM-generated Pydantic schema missing a field its ORM model required, a deterministic bug no amount of the framework's own retrying could ever fix) is what motivated this work.

**`backend/core/failure_classification.py`** — `classify_exception(error) -> FailureCategory` maps any exception onto a 15-value taxonomy (provider/validation/parsing/tool/context_overflow/timeout/network/authentication/database/workspace/mcp/filesystem/serialization/state_corruption/prompt_construction/unknown), unwrapping `LLMError.__cause__` first since `LLMService.invoke()` always `raise ... from error` — the *original* provider exception is far more specific than the generic wrapper. `is_likely_retryable(category)` flags only provider/timeout/network/database as genuinely retry-worthy. `to_recovery_reason(...)` maps this (plus non-exception failures `classify_exception` never sees — a failing pytest run or a rejected review score isn't a raised exception) onto a coarser, user-facing `RecoveryReason` shown in the Recovery Panel. `failure_signature(...)` hashes agent+reason+message so two consecutive failures with the same signature can be flagged as "the last repair didn't change anything" — observational only, this never touches `MAX_TEST_RETRIES`/`MAX_REVIEW_RETRIES`.

**Per-invocation instrumentation — `backend/graph/builder.py::_wrap_with_events`.** This wrapper already surrounded every node with `AGENT_STARTED`/`AGENT_COMPLETED` events but had no failure visibility at all (`result = fn(state)` was unguarded — a raised exception just propagated through it). v1.6 adds a `try/except` around that call, times both paths, and emits a new `AGENT_INVOCATION_RECORDED` event (`backend/events/event_types.py`) carrying status, attempt number, provider/model/token/character counts (summed from a small `ContextVar[list[LLMCallInfo]]` in `backend/core/run_context.py` that `LLMService.invoke()` appends to per real LLM call — the same contextvar-per-thread idiom `mcp/executor.py` already used for `run_id` propagation, generalized into a neutral home), and on failure the classified category/reason, exception type, truncated stacktrace, and the checkpoint immediately preceding it. This is deliberately the *node* level, not `BaseAgent`, to keep the change to one file instead of touching all eight agent constructors. `DatabaseSyncService` persists each event into the new `agent_invocations` table (see [Database_Design.md](Database_Design.md)) — self-contained in its own metadata, so it's not one of the snapshot-triggering event types.

**Structured logging.** `backend/core/logging.py` now stamps every log line with `run=<id>` (or `run=-`) via a `logging.Filter` reading the same `run_id` contextvar, making `GET /runs/{id}/logs` a reliable grep instead of best-effort string matching.

**Recovery modes — `Application` (`backend/core/app.py`).** Four new methods, all reusing existing primitives rather than a new execution path:
- `retry_failed_agent(run_id)` / `restart_from_checkpoint(run_id, checkpoint_id)` — resumes the *same* run from an arbitrary earlier checkpoint via LangGraph's own `get_state`/`update_state` ("edit state and continue," not raw checkpoint-table access), clearing a committed `FAILED` status and retry counts on that checkpoint's state before resuming. `retry_failed_agent` auto-selects the latest checkpoint — honestly just a specialized `restart_from_checkpoint`, since the graph's single entry point means there's no way to re-run *only* the failed node in isolation. Correctly recomputing routing (not just replaying whatever routing decision was already committed at that checkpoint) requires passing `as_node` to `update_state`, derived from that checkpoint's own `execution.current_agent` — confirmed live: reset-in-place with no `as_node` resumed into an empty `next`, since the graph considered itself already finished at that checkpoint.
- `restart_workflow(project_id, latest_run_id)` — a genuinely fresh run (`RunService.seed_restart_state`, keeping only the original prompt) reusing the same workspace, backed up first (see [Database_Design.md](Database_Design.md)).
- `duplicate_and_retry(latest_run_id)` — a brand-new project seeded from the original prompt via the existing `start_project_run`, leaving the original untouched.

**Recommendation engine — `backend/services/recovery_recommendation.py`.** `recommend_action(reason, repeated_failure, mode_success_rates)` maps a `RecoveryReason` onto a `RecoveryMode` + confidence + explanation, from fixed priors (transient categories score high; parse/validation-rooted failures favor a fresh duplicate over a bare retry, since the model's own output is unlikely to differ; a repeated failure signature downgrades a retry recommendation in favor of a full restart) blended with real `AgentInvocationRepository` history once there's enough of it — never blocked on having data first.

**Static validation** is documented above, in "The Eight Agents," since it's a graph-topology change, not purely an observability one.

---

## Iterative Development (v1.5)

A follow-up message ("add authentication", "fix this bug") does **not** change the graph itself — every continuation still runs the exact same `Analysis → Planner → Architect → Developer → StaticValidation → Tester → (Debugger) → Reviewer → Documentation` pipeline, unconditionally, entering at Analysis exactly like a first-ever prompt does. This was a deliberate choice over the alternative (true conditional stage-skipping, e.g. jumping straight to Developer for a narrow fix): it's a much smaller, lower-risk change to a graph that's otherwise stable and well-tested, at the cost of a follow-up always paying for a full pipeline pass even when only one file needs to change. Two mechanisms do the real work of making that full pass behave like a targeted edit instead of a fresh regeneration:

**1. The Analysis agent merges instead of replacing, on a follow-up.** `ContextManager._build_analysis_context()` already sent Analysis the full `Conversation History` and `Current Project State` before v1.5 — no plumbing changed there. What changed is `backend/prompts/analysis.md`, which now has an explicit instruction: if the conversation has more than one message, treat `Current Project State` as the accepted baseline and return a *merged, updated* spec — appending new requirements for an additive request ("add tests"), updating only the named field for a replacement request ("replace PostgreSQL with MySQL"), and leaving everything else untouched for a narrow request ("fix this bug", which may not need `requirements`/`tech_stack` to change at all). `AnalysisAgent.update_state()` itself is unchanged (still assigns the LLM's full output as the new spec) — correctness now rests entirely on the prompt producing a proper superset, which is real prompt-engineering surface, not a one-time fix; it was validated once against a real follow-up ("add a multiply function" onto an existing "add function" project) and produced a sensible merged result, but should be expected to need further tuning against a wider variety of real follow-ups.

**2. Every other agent gets a lightweight intent hint, not full conversation access.** `ContextManager.build_context()` gained one small, single-point addition: for any agent other than Analysis, when the conversation has more than one message, it appends a `"Latest Follow-up Request"` section containing just the newest message. This is the entire "intent-scoped full pass" mechanism — Planner/Architect/Developer/etc. still run in full, but now know what this specific turn is actually about and can naturally scope their own output to it, rather than reprocessing the whole project from a position of ignorance about what just changed.

**State reset/carry-forward on continuation** (`RunService.seed_continuation_state()`, called by `Application.start_project_run()` when `project_id` is given): `conversation.messages` is appended to, never replaced; `project`/`planning`/`architecture`/`implementation.written_files`/`knowledge.entries` carry forward as durable context; `testing`/`debug`/`review` reset to fresh defaults (every follow-up gets a full re-test/re-review of the current state); `execution.*` (status, retry counters, current agent/step, timestamps) resets for a genuinely new pass. This relies on `MaterializationService`'s pre-existing additive-write behavior (unions newly-written paths with `previous_written_files`, already used for repair passes and resumed workflows) — carrying `implementation.written_files` forward is what makes a Developer pass that only touches one file leave every other previously-generated file exactly as it was, both in `state.json` and on disk.

See [API_Design.md](API_Design.md#projects--iterative-development-v15) for the REST surface (`POST /projects`, `POST /projects/{id}/messages`) and [Database_Design.md](Database_Design.md) for the `Project` entity and workspace-directory changes this all depends on.

---

## Design Principles

* Single responsibility per agent, with a hard boundary between "the LLM decides" and "Python executes" for anything that touches the filesystem or a real process (file writes, test execution).
* Structured, Pydantic-validated output only — every agent's `validate()` parses and schema-validates the LLM's JSON response before it ever touches `WorkflowState`.
* Shared, centralized context assembly and knowledge storage — no agent duplicates selection logic.
* Retry loops are bounded and evidence-driven, never based on an agent's own claim of success.
* MCP tool access is explicit, per-agent, and deny-by-default (currently granted only to Documentation).
* Every new agent capability (context manager, knowledge manager, MCP kwargs) was added as an optional constructor parameter with a backward-compatible default, so unaffected agents' behavior and tests are provably unchanged.