# State Management

## Overview

AgentForge uses a single root Pydantic model, `WorkflowState` (`backend/state/workflow_state.py`), composed of eleven nested state models. It is the only object LangGraph threads through every node, the only object ever checkpointed, and the only object `RunService` persists to disk. There is no separate database row or ORM model — `WorkflowState.model_dump_json()` / `model_validate_json()` is the entire persistence contract for run state.

Each nested state is owned by one or more specific agents/nodes; other agents may read it (through `ContextManager`) but do not write to it.

---

## State Composition

```text
                              WorkflowState
                                    │
    ┌───────────┬───────────┬──────┼──────┬──────────┬───────────┬─────────┬────────────┬───────────┬───────────┐
    ▼           ▼           ▼      ▼      ▼          ▼           ▼         ▼            ▼           ▼           ▼
conversation  project   planning architecture implementation testing  debug    review   documentation knowledge  execution
```

```python
class WorkflowState(BaseModel):
    conversation: ConversationState
    project: ProjectState
    planning: PlanningState
    architecture: ArchitectureState
    implementation: ImplementationState
    testing: TestingState
    debug: DebugState
    review: ReviewState
    documentation: DocumentationState
    knowledge: KnowledgeState
    execution: ExecutionState
```

All fields have `default_factory`s, so `WorkflowState()` alone is a valid, fully-initialized empty state — used by `RunService.create_run()` before Analysis has run.

---

## `ConversationState`

Owner: seeded by the CLI, read by every agent's context.

| Field | Type | Notes |
|---|---|---|
| `messages` | `list[BaseMessage]` | The actual LangChain message objects (`HumanMessage`, etc.); `arbitrary_types_allowed=True`. |
| `summary` | `str \| None` | Condensed summary (unused by any agent today, reserved). |
| `pending_questions` | `list[str]` | Questions still requiring user input. |

## `ProjectState`

Owner: Analysis.

`project_name`, `project_description`, `objective`, `requirements: list[str]`, `backend`/`frontend`/`database`/`deployment` (inferred tech stack), `target_audience`, `pending_clarifications`, `tech_stack: list[str]`, `output_directory` (set by `Application.start_run` to `workspace/<run_id>`), `status: ProjectStatus` (NEW/ANALYZED/PLANNED/IN_PROGRESS/COMPLETED), timestamps.

## `PlanningState`

Owner: Planner.

`tasks: list[Task]` (id, title, description, `dependencies`, `milestone`, `is_completed`), `milestones: list[Milestone]`, `risks: list[Risk]` (with `mitigation`), `assumptions`, `dependencies`. A `model_validator` enforces unique IDs, that every task dependency/milestone reference resolves to a real entry, and — via DFS — that the task graph has **no dependency cycles**, rejected at construction time.

## `ArchitectureState`

Owner: Architect.

`architecture_summary`, `system_design: SystemDesign` (layers + communication flow), `folder_structure` (nested dict), `api_design: APIDesign` (style + `Endpoint` list, HTTP method validated, uniqueness enforced), `components: list[Component]` (name-unique, validated), `database_design: DatabaseDesign`, `design_patterns`, `architecture_decisions: list[ArchitectureDecision]` (id-unique; `status`: proposed/accepted/rejected/deprecated/superseded).

## `ImplementationState`

Owner: Developer (LLM output) + `MaterializationService` (disk-write results).

`generated_code: list[GeneratedCode]` (path, full `content`, `language`) — set by the LLM. `written_files` and `file_write_errors` are **system-controlled only**: set exclusively by `MaterializationService` after a real write attempt, never by the agent. `completed_tasks`/`failed_tasks`/`implementation_notes`.

## `TestingState`

Owner: Tester (proposes `command` only) + `TestingService` (everything else, from a real subprocess run).

`status: TestStatus` (not_run/passed/failed/error/timeout), `command: list[str] \| None`, `exit_code`, `stdout`/`stderr` (possibly truncated at `MAX_TEST_OUTPUT_CHARS`), `passed: bool`, `total_tests`/`passed_tests`/`skipped_tests`, `failed_tests: list[TestFailure]`, `duration_seconds`, `timed_out`, `attempt_number`, `error_type` (e.g. `command_rejected`), `testing_summary`. A `model_validator` enforces internal consistency — `passed` cannot be `True` alongside a FAILED/ERROR/TIMEOUT status or any recorded failure, and the passed/failed/skipped counts can never exceed `total_tests`.

## `DebugState`

Owner: Debugger.

`failure_summary`, `root_cause`, `failure_category: FailureCategory` (code_defect/test_defect/dependency_issue/environment_issue/configuration_issue/unknown), `affected_files`, `repair_instructions`, `suggested_changes: list[SuggestedChange]` (per-file), `confidence` (0.0–1.0), `attempt_number`, `debug_summary`. Never asserts a repair succeeded — that can only be confirmed by a subsequent real `TestingState` run.

## `ReviewState`

Owner: Reviewer.

`passed: bool`, `score` (0.0–10.0), `issues: list[ReviewIssue]` (capped at 15; each has `severity: Severity` — critical/high/medium/low/info), `strengths` (capped at 8), `recommendations` (capped at 8), `review_summary`. A `model_validator` enforces the actual approval rule: `passed` cannot be `True` if any issue has `CRITICAL` or `HIGH` severity, regardless of what the LLM's JSON claims.

## `DocumentationState`

Owner: Documentation.

`generated_docs: list[DocumentationFile]` (title/path/content, capped at 6), `documentation_summary`, `pending_documentation` (capped at 10). `extra="forbid"` on both models — an unexpected field from the LLM's JSON fails validation loudly rather than being silently dropped.

## `KnowledgeState`

Owner: written by Architect/Developer/Reviewer/the Tester node via `KnowledgeManager`; read by five agents.

`entries: list[KnowledgeEntry]` — every fact ever recorded this run, active and superseded. Each `KnowledgeEntry` has `category: KnowledgeCategory` (9 values: architecture_decision, technology_stack, project_convention, api_decision, database_decision, coding_standard, assumption, known_limitation, completed_milestone), `title`, `content`, `created_by`, `status: KnowledgeStatus` (active/superseded), `source_id` (dedup key), `supersedes` (links a replacement to the entry it replaces). See [Agent_Design.md](Agent_Design.md#shared-project-knowledge) for how this is populated and retrieved.

## `ExecutionState`

Owner: `BaseAgent`/`WorkflowNodes`/the graph builder — the workflow's own bookkeeping, not any single agent's output.

`workflow_status: WorkflowStatus` (initialized/running/waiting_for_user/completed/failed), `current_agent: AgentType | None`, `current_step`, `review_retry_count`, `test_retry_count`, `last_repair_trigger: RepairTrigger` (none/test_failure/review_feedback), `error_message`, `started_at`, `completed_at`.

---

## State Ownership Summary

| State model | Written by |
|---|---|
| `ConversationState` | CLI (seed), read-only elsewhere |
| `ProjectState` | Analysis |
| `PlanningState` | Planner |
| `ArchitectureState` | Architect |
| `ImplementationState` | Developer (code) + `MaterializationService` (write results) |
| `TestingState` | Tester (command) + `TestingService` (real execution result) |
| `DebugState` | Debugger |
| `ReviewState` | Reviewer |
| `DocumentationState` | Documentation |
| `KnowledgeState` | Architect, Developer, Reviewer, Tester node (via `KnowledgeManager`) |
| `ExecutionState` | `BaseAgent`, `WorkflowNodes`, `WorkflowBuilder` |

Every agent is only *allowed* to write its own state model in `update_state()`; nothing enforces this at the type level, but it's a consistent convention across all eight agents.

---

## Checkpointing and Resume

LangGraph's own `SqliteSaver` (`backend/services/checkpoint_service.py`), one SQLite database per run at `.agentforge/runs/<run_id>/checkpoints.sqlite`, checkpoints `WorkflowState` after every node. A custom `JsonPlusSerializer` is configured with an explicit allow-list of every Pydantic/enum class reachable from `WorkflowState` (walked recursively via `model_fields`) plus the concrete LangChain message classes — nothing outside that closure can be deserialized from a checkpoint.

`agentforge resume <run_id>` calls `graph.invoke(None, config={"configurable": {"thread_id": run_id}})` — passing `None` state tells LangGraph to resume from the last checkpoint for that `thread_id` rather than starting fresh. Already-completed nodes are not re-executed. This has been proven to work correctly across a genuine process restart, including mid-repair and with a real MCP tool call before and after the interruption.

**Never checkpointed, by construction:** `MCPClientManager`, any FastMCP `Client`, `MCPToolExecutor`, or any other runtime/connection object. None of these are fields anywhere on `WorkflowState` — a resumed run's `Application` builds all of this fresh in the new process.

---

## Persistence Strategy

Two independent mechanisms, both scoped per-run under `.agentforge/runs/<run_id>/` — see [Database_Design.md](Database_Design.md) for the full file layout:

* **`RunService`** — atomically writes the full `WorkflowState` as human-readable `state.json` after every graph invocation. This is what `agentforge status`/`inspect`/`runs` read; it does not participate in resume.
* **`CheckpointService`** — LangGraph's own SQLite-backed checkpoint log, used exclusively by `agentforge resume` to replay execution.

The two are redundant by design: `state.json` is for humans and quick inspection, the checkpoint database is for LangGraph's own replay mechanism. A run's generated code/docs are additionally materialized as real files under `workspace/<run_id>/` by `MaterializationService` — the `WorkflowState.implementation.generated_code` field holds file contents in memory/JSON, but the authoritative on-disk project is what `MaterializationService` actually wrote (`written_files`).

Since v0.11, a third, optional mechanism exists: `DatabaseSyncService` mirrors summary fields from `WorkflowState` (execution status, project metadata, knowledge entries) plus every `WorkflowEvent` into PostgreSQL, purely as a queryable index for the API layer's `GET /runs`/`GET /runs/{id}/knowledge` endpoints. It is not a fourth copy of `WorkflowState` itself (no full state blob, no generated code, is ever written to PostgreSQL) and it is never read from during workflow execution or resume — see [Database_Design.md](Database_Design.md).

---

## Design Principles

* Single source of truth: everything about a run's progress lives in one `WorkflowState`, never duplicated into a separate database schema.
* Every state model is Pydantic-validated at construction — invalid LLM output (bad enum value, broken cross-reference, contradictory `passed`/issue combination) fails loudly before it can enter the graph.
* Strict ownership: each state model has one clear writer; agents read others' sections through `ContextManager`, never by reaching into `WorkflowState` directly inside a prompt-building step.
* Fields that must reflect *real* execution (`written_files`, `TestingState`'s result fields) are explicitly system-controlled, documented as such in the model itself, and never touched by agent-authored code paths.
* Nothing that can't survive a fresh Python process (open connections, MCP clients) is ever part of `WorkflowState` — this is what makes cross-process resume possible at all.
* The optional PostgreSQL metadata mirror (v0.11) is a read path for the API layer only — it is never consulted by `graph.invoke()`, `RunService`, or `CheckpointService`, so a missing or unreachable database cannot affect workflow execution, resume, or the CLI.