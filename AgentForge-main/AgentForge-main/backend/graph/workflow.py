from enum import Enum


class WorkflowNode(str, Enum):
    ANALYSIS = "analysis"

    PLANNER = "planner"

    ARCHITECT = "architect"

    DEVELOPER = "developer"

    STATIC_VALIDATION = "static_validation"

    TESTER = "tester"

    DEBUGGER = "debugger"

    REVIEWER = "reviewer"

    DOCUMENTATION = "documentation"