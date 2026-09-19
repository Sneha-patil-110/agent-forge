# Output Format

## Purpose

This document defines the universal output rules for every AgentForge agent.

Every agent must produce structured, deterministic, and machine readable outputs that can be directly consumed by downstream agents and the workflow engine.

The primary objective is reliability, not conversational quality.

---

# General Rules

Always:

* Return only the requested output.
* Follow the expected schema exactly.
* Produce deterministic responses.
* Preserve existing state unless instructed to update it.
* Return valid structured data.

Never:

* Add conversational text.
* Add greetings.
* Add explanations.
* Add markdown unless explicitly requested.
* Add reasoning outside the expected schema.

---

# State Updates

Agents must only update the state they own.

Read only states must never be modified.

Example:

Requirement Analysis Agent

Writable:

* ProjectState

Read Only:

* ConversationState

---

Planner Agent

Writable:

* PlanningState

Read Only:

* ProjectState
* ConversationState

---

Architect Agent

Writable:

* ArchitectureState

Read Only:

* ProjectState
* PlanningState
* ConversationState

---

Developer Agent

Writable:

* ImplementationState

Read Only:

* ProjectState
* PlanningState
* ArchitectureState
* ConversationState

---

Reviewer Agent

Writable:

* ReviewState

Read Only:

* ProjectState
* PlanningState
* ArchitectureState
* ImplementationState

---

Documentation Agent

Writable:

* DocumentationState

Read Only:

* ProjectState
* PlanningState
* ArchitectureState
* ImplementationState
* ReviewState

---

# Structured Output

Outputs must conform to the corresponding Pydantic state model.

Every field should satisfy its declared type.

Missing optional values should remain null or use default values.

Do not invent fields that do not exist in the schema.

---

# Data Integrity

Always:

* Preserve existing valid information.
* Update only fields that require changes.
* Avoid overwriting unrelated data.
* Keep outputs internally consistent.

---

# Collections

Lists should:

* Preserve logical ordering.
* Avoid duplicate entries.
* Contain only relevant items.
* Follow the expected item schema.

---

# Text Generation

Generated text should:

* Be concise.
* Be technically accurate.
* Be consistent with project terminology.
* Avoid unnecessary repetition.

---

# File Generation

When generating files:

* Produce complete file contents.
* Use valid project paths.
* Preserve directory structure.
* Ensure file content is internally consistent.

---

# Error Handling

If required information is missing:

* Do not guess.
* Record the missing information when appropriate.
* Generate clarification questions if supported by the agent.
* Return a valid state object.

Never return partially corrupted outputs.

---

# Consistency Rules

Outputs must remain consistent with:

* ProjectState
* PlanningState
* ArchitectureState
* Previous workflow decisions

Agents must never contradict upstream states without explicit user instructions.

---

# Validation Checklist

Before returning an output, verify:

* The output matches the expected state model.
* Only writable fields were modified.
* No unsupported assumptions were introduced.
* All required fields are valid.
* The response is deterministic.
* The output is immediately usable by the next workflow step.
