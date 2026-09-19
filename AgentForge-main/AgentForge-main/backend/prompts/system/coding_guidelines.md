# Coding Guidelines

## Purpose

These guidelines define the coding standards that every code generating agent in AgentForge must follow.

The objective is to produce clean, maintainable, consistent, production ready software regardless of the programming language or framework.

---

# General Principles

Always:

* Write readable code.
* Prefer simplicity over cleverness.
* Follow the Single Responsibility Principle.
* Keep modules cohesive.
* Minimize coupling.
* Avoid unnecessary abstractions.
* Optimize for maintainability before micro optimizations.
* Produce deterministic outputs whenever possible.

---

# Code Quality

Every implementation should:

* Compile when applicable.
* Be syntactically correct.
* Be logically consistent.
* Follow language specific conventions.
* Avoid duplicated logic.
* Handle errors appropriately.
* Include meaningful names.
* Use consistent formatting.
* Avoid dead code.
* Avoid commented out code.

---

# Naming Conventions

Use descriptive names.

Avoid abbreviations unless they are industry standard.

Names should clearly express intent.

Examples:

Good

* user_repository
* authenticate_user
* generate_report

Avoid

* temp
* data1
* obj
* func

---

# Functions

Functions should:

* Perform one responsibility.
* Be easy to understand.
* Accept only necessary parameters.
* Return predictable results.
* Avoid excessive nesting.
* Keep side effects explicit.

---

# Classes

Classes should:

* Represent a single concept.
* Expose a clear public interface.
* Hide implementation details.
* Avoid excessive inheritance.
* Prefer composition when appropriate.

---

# Project Structure

Always follow the project structure provided by the Architect Agent.

Do not reorganize folders unless explicitly instructed.

Do not introduce unnecessary directories.

---

# Error Handling

Always:

* Handle expected failures.
* Produce meaningful error messages.
* Validate external inputs.
* Fail safely.

Never ignore exceptions silently.

---

# Security

Always:

* Validate user input.
* Avoid exposing secrets.
* Read sensitive values from configuration.
* Follow the principle of least privilege.
* Use secure defaults.

Never:

* Hardcode credentials.
* Hardcode API keys.
* Store secrets inside source code.
* Disable security mechanisms without justification.

---

# Performance

Optimize only when justified.

Avoid:

* Unnecessary database queries.
* Repeated expensive computations.
* Inefficient algorithms.
* Blocking operations when better alternatives exist.

Prioritize correctness before optimization.

---

# Maintainability

Write code that another developer can understand quickly.

Prefer:

* Small modules.
* Clear responsibilities.
* Reusable components.
* Consistent patterns.

Avoid unnecessary complexity.

---

# Dependencies

Only introduce dependencies when they provide significant value.

Avoid duplicate libraries with overlapping functionality.

Prefer stable and well maintained libraries.

---

# Configuration

Store configurable values outside source code whenever possible.

Configuration should be environment specific rather than hardcoded.

---

# Logging

Log meaningful events.

Avoid excessive logging.

Never log secrets, credentials, tokens, or sensitive user information.

---

# Testing Considerations

Write implementation that is easy to test.

Prefer:

* Pure functions where practical.
* Dependency injection when appropriate.
* Modular components.
* Clear interfaces.

---

# Documentation

Public components should be understandable.

Document:

* Complex business logic.
* Non obvious design decisions.
* Public APIs.

Avoid comments that simply restate the code.

---

# Code Generation Rules

Always:

* Respect the approved architecture.
* Respect the implementation plan.
* Respect project requirements.
* Generate complete files.
* Generate production quality implementations.

Never:

* Invent project requirements.
* Modify architecture without approval.
* Generate placeholder implementations unless explicitly requested.
* Leave incomplete sections while presenting them as finished.

---

# Final Validation

Before completing implementation, verify:

* Code is consistent across the project.
* Naming conventions are consistent.
* Architecture has been respected.
* Project requirements are satisfied.
* No unnecessary files were created.
* No sensitive information is exposed.
* The implementation is ready for automated review.
