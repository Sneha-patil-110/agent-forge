from __future__ import annotations

import argparse
import sys

from backend.cli.commands import (
    cmd_create,
    cmd_doctor,
    cmd_docs,
    cmd_inspect,
    cmd_mcp_health,
    cmd_mcp_inspect,
    cmd_mcp_list,
    cmd_mcp_execute,
    cmd_mcp_refresh,
    cmd_mcp_test,
    cmd_mcp_tools,
    cmd_replay,
    cmd_resume,
    cmd_runs,
    cmd_status,
)
from backend.core.logging import setup_logging


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentforge",
        description="AgentForge: an autonomous software engineering system.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser(
        "create", help="Create and run a new AgentForge workflow."
    )
    create_parser.add_argument(
        "request", help="Natural language description of the software to build."
    )
    create_parser.set_defaults(handler=cmd_create)

    resume_parser = subparsers.add_parser(
        "resume", help="Resume an interrupted AgentForge run."
    )
    resume_parser.add_argument("run_id", help="Run ID to resume.")
    resume_parser.set_defaults(handler=cmd_resume)

    status_parser = subparsers.add_parser(
        "status", help="Show a lightweight summary of one run."
    )
    status_parser.add_argument("run_id", help="Run ID to inspect.")
    status_parser.set_defaults(handler=cmd_status)

    runs_parser = subparsers.add_parser("runs", help="List known AgentForge runs.")
    runs_parser.set_defaults(handler=cmd_runs)

    inspect_parser = subparsers.add_parser(
        "inspect", help="Show a detailed, safe summary of one run."
    )
    inspect_parser.add_argument("run_id", help="Run ID to inspect.")
    inspect_parser.set_defaults(handler=cmd_inspect)

    docs_parser = subparsers.add_parser(
        "docs", help="List or view a run's generated documentation."
    )
    docs_parser.add_argument("run_id", help="Run ID to inspect.")
    docs_parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Relative path of a specific document to view; omit to list all.",
    )
    docs_parser.add_argument(
        "--metadata",
        action="store_true",
        help="Show the document's metadata instead of its content.",
    )
    docs_parser.add_argument(
        "--output",
        metavar="FILE",
        help="Write the document's content to FILE instead of stdout.",
    )
    docs_parser.set_defaults(handler=cmd_docs)

    doctor_parser = subparsers.add_parser(
        "doctor", help="Deterministically diagnose a run from persisted evidence (never calls an LLM)."
    )
    doctor_parser.add_argument("run_id", help="Run ID to diagnose.")
    doctor_parser.set_defaults(handler=cmd_doctor)

    replay_parser = subparsers.add_parser(
        "replay", help="Re-run the testing pipeline against a saved run's repository, without regenerating it."
    )
    replay_parser.add_argument("run_id", help="Run ID whose repository/state to replay.")
    replay_parser.add_argument(
        "--from",
        dest="from_stage",
        default="testing",
        choices=["testing"],
        help="Which stage to replay from (only 'testing' is supported today).",
    )
    replay_parser.set_defaults(handler=cmd_replay)

    mcp_parser = subparsers.add_parser(
        "mcp", help="Inspect and manage configured MCP servers."
    )
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command", required=True)

    mcp_list_parser = mcp_subparsers.add_parser("list", help="List configured MCP servers.")
    mcp_list_parser.set_defaults(handler=cmd_mcp_list)

    mcp_inspect_parser = mcp_subparsers.add_parser("inspect", help="Show details for one MCP server.")
    mcp_inspect_parser.add_argument("server_name")
    mcp_inspect_parser.set_defaults(handler=cmd_mcp_inspect)

    mcp_tools_parser = mcp_subparsers.add_parser("tools", help="List available MCP tools.")
    mcp_tools_parser.add_argument(
        "server_name", nargs="?", default=None, help="Limit to this server's tools; omit for all servers."
    )
    mcp_tools_parser.add_argument(
        "--query", default=None, help="Filter tools by a name/description substring."
    )
    mcp_tools_parser.set_defaults(handler=cmd_mcp_tools)

    mcp_test_parser = mcp_subparsers.add_parser("test", help="Test connectivity to one MCP server.")
    mcp_test_parser.add_argument("server_name")
    mcp_test_parser.set_defaults(handler=cmd_mcp_test)

    mcp_health_parser = mcp_subparsers.add_parser("health", help="Show health status for MCP servers.")
    mcp_health_parser.add_argument(
        "server_name", nargs="?", default=None, help="Check only this server; omit to check every enabled server."
    )
    mcp_health_parser.set_defaults(handler=cmd_mcp_health)

    mcp_refresh_parser = mcp_subparsers.add_parser(
        "refresh", help="Re-discover tools for every enabled MCP server."
    )
    mcp_refresh_parser.set_defaults(handler=cmd_mcp_refresh)

    mcp_execute_parser = mcp_subparsers.add_parser(
        "execute", help="Call a single MCP tool directly (bypasses agent permission grants)."
    )
    mcp_execute_parser.add_argument("tool_identity", help="'<server>.<tool>', e.g. context7.resolve-library-id")
    mcp_execute_parser.add_argument(
        "--args", default=None, help="Tool arguments as a JSON object, e.g. '{\"key\": \"value\"}'."
    )
    mcp_execute_parser.set_defaults(handler=cmd_mcp_execute)

    return parser


def main(argv: list[str] | None = None) -> int:
    setup_logging()

    parser = _build_parser()
    args = parser.parse_args(argv)

    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
