
from __future__ import annotations

from fastmcp import FastMCP

server = FastMCP("agentforge-test-server")


@server.tool
def echo(message: str) -> str:
    """Echo back the given message."""

    return message


@server.tool
def add(a: int, b: int) -> int:
    """Add two integers."""

    return a + b


@server.tool
def get_test_document(topic: str) -> str:
    """Return a short canned document about ``topic``."""

    return f"# {topic}\n\nThis is a test document about {topic}."


if __name__ == "__main__":
    server.run()
