from __future__ import annotations

import argparse

import pytest

from backend.cli import main


def test_help_exits_cleanly() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main.main(["--help"])

    assert excinfo.value.code == 0


def test_missing_command_exits_nonzero() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main.main([])

    assert excinfo.value.code != 0


def test_unknown_command_exits_nonzero() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main.main(["not-a-real-command"])

    assert excinfo.value.code != 0


def test_create_dispatches_to_cmd_create(monkeypatch) -> None:
    calls = []

    def fake_cmd_create(args: argparse.Namespace) -> int:
        calls.append(args.request)
        return 0

    monkeypatch.setattr(main, "cmd_create", fake_cmd_create)

    exit_code = main.main(["create", "Build a FastAPI expense tracker"])

    assert exit_code == 0
    assert calls == ["Build a FastAPI expense tracker"]


def test_resume_dispatches_to_cmd_resume(monkeypatch) -> None:
    calls = []

    def fake_cmd_resume(args: argparse.Namespace) -> int:
        calls.append(args.run_id)
        return 3

    monkeypatch.setattr(main, "cmd_resume", fake_cmd_resume)

    exit_code = main.main(["resume", "af_20260714_deadbeef"])

    assert exit_code == 3
    assert calls == ["af_20260714_deadbeef"]


def test_status_requires_run_id_argument() -> None:
    with pytest.raises(SystemExit):
        main.main(["status"])


def test_runs_dispatches_to_cmd_runs(monkeypatch) -> None:
    calls = []

    def fake_cmd_runs(args: argparse.Namespace) -> int:
        calls.append(True)
        return 0

    monkeypatch.setattr(main, "cmd_runs", fake_cmd_runs)

    exit_code = main.main(["runs"])

    assert exit_code == 0
    assert calls == [True]


def test_inspect_dispatches_to_cmd_inspect(monkeypatch) -> None:
    calls = []

    def fake_cmd_inspect(args: argparse.Namespace) -> int:
        calls.append(args.run_id)
        return 0

    monkeypatch.setattr(main, "cmd_inspect", fake_cmd_inspect)

    exit_code = main.main(["inspect", "af_20260714_deadbeef"])

    assert exit_code == 0
    assert calls == ["af_20260714_deadbeef"]


def test_docs_dispatches_to_cmd_docs_with_defaults(monkeypatch) -> None:
    calls = []

    def fake_cmd_docs(args: argparse.Namespace) -> int:
        calls.append((args.run_id, args.path, args.metadata, args.output))
        return 0

    monkeypatch.setattr(main, "cmd_docs", fake_cmd_docs)

    exit_code = main.main(["docs", "af_20260714_deadbeef"])

    assert exit_code == 0
    assert calls == [("af_20260714_deadbeef", None, False, None)]


def test_docs_dispatches_with_path_metadata_and_output_flags(monkeypatch) -> None:
    calls = []

    def fake_cmd_docs(args: argparse.Namespace) -> int:
        calls.append((args.run_id, args.path, args.metadata, args.output))
        return 0

    monkeypatch.setattr(main, "cmd_docs", fake_cmd_docs)

    exit_code = main.main(
        ["docs", "af_20260714_deadbeef", "README.md", "--metadata", "--output", "out.md"]
    )

    assert exit_code == 0
    assert calls == [("af_20260714_deadbeef", "README.md", True, "out.md")]


def test_mcp_requires_a_subcommand() -> None:
    with pytest.raises(SystemExit):
        main.main(["mcp"])


def test_mcp_list_dispatches_to_cmd_mcp_list(monkeypatch) -> None:
    calls = []

    def fake_cmd_mcp_list(args: argparse.Namespace) -> int:
        calls.append(True)
        return 0

    monkeypatch.setattr(main, "cmd_mcp_list", fake_cmd_mcp_list)

    exit_code = main.main(["mcp", "list"])

    assert exit_code == 0
    assert calls == [True]


def test_mcp_inspect_dispatches_with_server_name(monkeypatch) -> None:
    calls = []

    def fake_cmd_mcp_inspect(args: argparse.Namespace) -> int:
        calls.append(args.server_name)
        return 0

    monkeypatch.setattr(main, "cmd_mcp_inspect", fake_cmd_mcp_inspect)

    exit_code = main.main(["mcp", "inspect", "docs"])

    assert exit_code == 0
    assert calls == ["docs"]


def test_mcp_tools_dispatches_with_optional_server_and_query(monkeypatch) -> None:
    calls = []

    def fake_cmd_mcp_tools(args: argparse.Namespace) -> int:
        calls.append((args.server_name, args.query))
        return 0

    monkeypatch.setattr(main, "cmd_mcp_tools", fake_cmd_mcp_tools)

    exit_code = main.main(["mcp", "tools", "docs", "--query", "search"])

    assert exit_code == 0
    assert calls == [("docs", "search")]


def test_mcp_test_dispatches_with_server_name(monkeypatch) -> None:
    calls = []

    def fake_cmd_mcp_test(args: argparse.Namespace) -> int:
        calls.append(args.server_name)
        return 0

    monkeypatch.setattr(main, "cmd_mcp_test", fake_cmd_mcp_test)

    exit_code = main.main(["mcp", "test", "docs"])

    assert exit_code == 0
    assert calls == ["docs"]


def test_mcp_health_dispatches_with_optional_server_name(monkeypatch) -> None:
    calls = []

    def fake_cmd_mcp_health(args: argparse.Namespace) -> int:
        calls.append(args.server_name)
        return 0

    monkeypatch.setattr(main, "cmd_mcp_health", fake_cmd_mcp_health)

    exit_code = main.main(["mcp", "health"])

    assert exit_code == 0
    assert calls == [None]


def test_mcp_refresh_dispatches_to_cmd_mcp_refresh(monkeypatch) -> None:
    calls = []

    def fake_cmd_mcp_refresh(args: argparse.Namespace) -> int:
        calls.append(True)
        return 0

    monkeypatch.setattr(main, "cmd_mcp_refresh", fake_cmd_mcp_refresh)

    exit_code = main.main(["mcp", "refresh"])

    assert exit_code == 0
    assert calls == [True]
