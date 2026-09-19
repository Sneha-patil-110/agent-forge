
from __future__ import annotations

from datetime import UTC, datetime

from fastmcp import FastMCP

server = FastMCP("agentforge-local-tools")


@server.tool
def current_time() -> str:
    """Return the current UTC time in ISO 8601 format."""

    return datetime.now(UTC).isoformat()


@server.tool
def echo(message: str) -> str:
    """Echo back the given message."""

    return message


@server.tool
def word_count(text: str) -> int:
    """Count the number of whitespace-separated words in the given text."""

    return len(text.split())


if __name__ == "__main__":
    server.run()
