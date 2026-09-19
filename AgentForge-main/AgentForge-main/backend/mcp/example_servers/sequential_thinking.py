
from __future__ import annotations

from fastmcp import FastMCP

server = FastMCP("agentforge-sequential-thinking")

_thought_history: list[dict] = []
_branches: dict[str, list[dict]] = {}


@server.tool(
    description=(
        "A detailed tool for dynamic and reflective problem-solving through thoughts. "
        "This tool helps analyze problems through a flexible thinking process that can "
        "adapt and evolve. Each thought can build on, question, or revise previous "
        "insights as understanding deepens. Use it for breaking down complex problems "
        "into steps, planning and design with room for revision, analysis that might "
        "need course correction, and situations where the full scope isn't clear "
        "upfront. Set nextThoughtNeeded to false only when a satisfactory answer has "
        "been reached."
    )
)
def sequentialthinking(
    thought: str,
    nextThoughtNeeded: bool,
    thoughtNumber: int,
    totalThoughts: int,
    isRevision: bool = False,
    revisesThought: int | None = None,
    branchFromThought: int | None = None,
    branchId: str | None = None,
    needsMoreThoughts: bool = False,
) -> dict:
    entry = {
        "thought": thought,
        "thoughtNumber": thoughtNumber,
        "totalThoughts": totalThoughts,
        "nextThoughtNeeded": nextThoughtNeeded,
        "isRevision": isRevision,
        "revisesThought": revisesThought,
        "branchFromThought": branchFromThought,
        "branchId": branchId,
        "needsMoreThoughts": needsMoreThoughts,
    }

    _thought_history.append(entry)

    if branchFromThought is not None and branchId is not None:
        _branches.setdefault(branchId, []).append(entry)

    return {
        "thoughtNumber": thoughtNumber,
        "totalThoughts": totalThoughts,
        "nextThoughtNeeded": nextThoughtNeeded,
        "branches": list(_branches.keys()),
        "thoughtHistoryLength": len(_thought_history),
    }


if __name__ == "__main__":
    server.run()
