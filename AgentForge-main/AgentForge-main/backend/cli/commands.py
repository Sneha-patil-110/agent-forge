
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from backend.cli.renderer import CLIEventRenderer
from backend.core.app import Application
from backend.core.exceptions import (
    AgentForgeException,
    InvalidRunIdError,
    MCPServerNotFoundError,
    RunCorruptedError,
    RunNotFoundError,
)
from backend.state.execution_state import WorkflowStatus

logger = logging.getLogger(__name__)

EXIT_SUCCESS = 0
EXIT_UNEXPECTED_ERROR = 1
EXIT_INVALID_ARGUMENT = 2
EXIT_RUN_NOT_FOUND = 3
EXIT_RUN_CORRUPTED = 4
EXIT_WORKFLOW_FAILED = 5
EXIT_INTERRUPTED = 130


def _print_error(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)


def _report_lookup_error(run_id: str, error: Exception) -> int:
    if isinstance(error, InvalidRunIdError):
        _print_error(str(error))
        return EXIT_INVALID_ARGUMENT

    if isinstance(error, RunNotFoundError):
        _print_error(f"Run not found: {run_id}")
        return EXIT_RUN_NOT_FOUND

    if isinstance(error, RunCorruptedError):
        _print_error(str(error))
        return EXIT_RUN_CORRUPTED

    logger.exception("Unexpected error looking up run %s", run_id)
    _print_error(f"Unexpected error: {error}")
    return EXIT_UNEXPECTED_ERROR


def cmd_create(args: argparse.Namespace) -> int:
    application = Application()
    application.event_dispatcher.subscribe(CLIEventRenderer())

    try:
        run_id, state = application.start_run(args.request)
    except KeyboardInterrupt as error:
        run_id = getattr(error, "run_id", None)
        if run_id:
            print(f"Interrupted. Resume later with: agentforge resume {run_id}")
        else:
            print("Interrupted before a run could be created.")
        return EXIT_INTERRUPTED
    except Exception as error:
        run_id = getattr(error, "run_id", None)
        logger.exception("Unexpected error creating run")
        if run_id:
            _print_error(f"{error} (run_id={run_id})")
        else:
            _print_error(str(error))
        return EXIT_UNEXPECTED_ERROR

    print(f"Run ID: {run_id}")
    print(f"Status: {state.execution.workflow_status.value}")

    if state.execution.workflow_status == WorkflowStatus.FAILED:
        if state.execution.error_message:
            _print_error(state.execution.error_message)
        return EXIT_WORKFLOW_FAILED

    return EXIT_SUCCESS


def cmd_resume(args: argparse.Namespace) -> int:
    application = Application()
    application.event_dispatcher.subscribe(CLIEventRenderer())

    try:
        state, already_terminal = application.resume_run(args.run_id)
    except KeyboardInterrupt:
        print(f"Interrupted. Resume later with: agentforge resume {args.run_id}")
        return EXIT_INTERRUPTED
    except (InvalidRunIdError, RunNotFoundError, RunCorruptedError) as error:
        return _report_lookup_error(args.run_id, error)
    except Exception as error:
        logger.exception("Unexpected error resuming run %s", args.run_id)
        _print_error(str(error))
        return EXIT_UNEXPECTED_ERROR

    if already_terminal:
        print(
            f"Run {args.run_id} is already "
            f"{state.execution.workflow_status.value}; nothing to resume."
        )
        return (
            EXIT_SUCCESS
            if state.execution.workflow_status == WorkflowStatus.COMPLETED
            else EXIT_WORKFLOW_FAILED
        )

    print(f"Run ID: {args.run_id}")
    print(f"Status: {state.execution.workflow_status.value}")

    if state.execution.workflow_status == WorkflowStatus.FAILED:
        if state.execution.error_message:
            _print_error(state.execution.error_message)
        return EXIT_WORKFLOW_FAILED

    return EXIT_SUCCESS


def cmd_status(args: argparse.Namespace) -> int:
    application = Application()

    try:
        metadata = application.run_service.load_metadata(args.run_id)
        state = application.run_service.load_state(args.run_id)
    except (InvalidRunIdError, RunNotFoundError, RunCorruptedError) as error:
        return _report_lookup_error(args.run_id, error)

    current_agent = (
        state.execution.current_agent.value
        if state.execution.current_agent
        else "-"
    )

    print(f"Run ID: {metadata.run_id}")
    print(f"Status: {state.execution.workflow_status.value}")
    print(f"Created: {metadata.created_at.isoformat()}")
    print(f"Updated: {metadata.updated_at.isoformat()}")
    print(f"Current step: {state.execution.current_step or '-'}")
    print(f"Current agent: {current_agent}")

    return EXIT_SUCCESS


def cmd_runs(args: argparse.Namespace) -> int:
    application = Application()
    run_ids = application.run_service.list_run_ids()

    if not run_ids:
        print("No runs found.")
        return EXIT_SUCCESS

    rows = []

    for run_id in run_ids:
        try:
            metadata = application.run_service.load_metadata(run_id)
        except (RunNotFoundError, RunCorruptedError):
            rows.append((run_id, "corrupted", None, None))
            continue

        try:
            state = application.run_service.load_state(run_id)
            status = state.execution.workflow_status.value
        except (RunNotFoundError, RunCorruptedError):
            status = "corrupted"

        rows.append((run_id, status, metadata.created_at, metadata.updated_at))

    rows.sort(
        key=lambda row: (row[3] is not None, row[3]),
        reverse=True,
    )

    print(f"{'RUN ID':<24} {'STATUS':<12} {'CREATED':<26} {'UPDATED':<26}")

    for run_id, status, created, updated in rows:
        created_str = created.isoformat() if created else "-"
        updated_str = updated.isoformat() if updated else "-"
        print(f"{run_id:<24} {status:<12} {created_str:<26} {updated_str:<26}")

    return EXIT_SUCCESS


def cmd_inspect(args: argparse.Namespace) -> int:
    application = Application()

    try:
        metadata = application.run_service.load_metadata(args.run_id)
        state = application.run_service.load_state(args.run_id)
    except (InvalidRunIdError, RunNotFoundError, RunCorruptedError) as error:
        return _report_lookup_error(args.run_id, error)

    current_agent = (
        state.execution.current_agent.value
        if state.execution.current_agent
        else "-"
    )
    completed_at = (
        state.execution.completed_at.isoformat()
        if state.execution.completed_at
        else "-"
    )
    if state.testing.passed:
        testing_result = "passed" if state.testing.tests_executed else "no_tests_discovered"
    else:
        testing_result = state.testing.status.value

    print(f"Run ID: {metadata.run_id}")
    print(f"Status: {state.execution.workflow_status.value}")
    print(f"Project name: {state.project.project_name or '-'}")
    print(f"Current step: {state.execution.current_step or '-'}")
    print(f"Current agent: {current_agent}")
    print(f"Test retry count: {state.execution.test_retry_count}")
    print(f"Review retry count: {state.execution.review_retry_count}")
    print(f"Dependency retry count: {state.execution.dependency_retry_count}")
    print(f"Testing result: {testing_result}")
    if state.testing.discovery_status:
        print(f"Discovery status: {state.testing.discovery_status.value}")
    print(f"Tests discovered: {state.testing.tests_discovered}")
    print(f"Tests executed: {state.testing.tests_executed}")
    print(f"Verification method: {state.testing.verification_method or '-'}")
    if state.testing.testing_summary:
        print(f"Testing summary: {state.testing.testing_summary}")
    print(
        f"Review result: {'passed' if state.review.passed else 'failed'} "
        f"(score={state.review.score}, attempt={state.review.attempt_number})"
    )
    if state.review.auto_passed:
        print(
            f"Review auto-passed with warnings: reason={state.review.auto_pass_reason} "
            f"({len(state.review.issues)} unresolved issue(s) -- see below)"
        )
    if state.review.issues:
        print("Review issues:")
        for issue in state.review.issues:
            location = f" [{issue.file_path}]" if issue.file_path else ""
            print(f"  - ({issue.severity.value}) {issue.title}{location}")
    print(f"Files materialized: {len(state.implementation.written_files)}")
    print(f"Created: {metadata.created_at.isoformat()}")
    print(f"Updated: {metadata.updated_at.isoformat()}")
    print(f"Started: {state.execution.started_at.isoformat()}")
    print(f"Completed: {completed_at}")
    print(f"Error: {state.execution.error_message or '-'}")

    return EXIT_SUCCESS


def cmd_replay(args: argparse.Namespace) -> int:

    from backend.services.replay_service import RepositoryNoLongerOnDiskError, ReplayService

    application = Application()
    replay_service = ReplayService(
        run_service=application.run_service,
        repository_integrity_validator=application.repository_integrity_validator,
        tester_node=application.nodes.tester,
    )

    try:
        result = replay_service.replay_from_testing(args.run_id)
    except (InvalidRunIdError, RunNotFoundError, RunCorruptedError) as error:
        return _report_lookup_error(args.run_id, error)
    except RepositoryNoLongerOnDiskError as error:
        _print_error(str(error))
        return EXIT_UNEXPECTED_ERROR

    if result.hash_mismatch_warning:
        print(f"WARNING: {result.hash_mismatch_warning}", file=sys.stderr)

    print(f"Replayed run {args.run_id}'s testing stage as new run {result.replay_run_id}.")
    print(f"Original run's evidence is untouched: agentforge doctor {args.run_id}")
    print(f"Replay result: agentforge doctor {result.replay_run_id}")
    print(f"Testing result: {'passed' if result.state.testing.passed else 'failed'}")

    if result.state.testing.classification:
        print(f"Classification: {result.state.testing.classification.value}")

    return EXIT_SUCCESS


def cmd_doctor(args: argparse.Namespace) -> int:

    application = Application()

    try:
        state = application.run_service.load_state(args.run_id)
    except (InvalidRunIdError, RunNotFoundError, RunCorruptedError) as error:
        return _report_lookup_error(args.run_id, error)

    from backend.services.run_doctor_service import RunDoctorService

    report = RunDoctorService().diagnose(run_id=args.run_id, state=state)

    label_width = max(len(label) for label, _ in report.stages) + 4

    for label, stage_status in report.stages:
        print(f"{label:<{label_width}} {stage_status}")

    from backend.state.execution_state import FailureCategory

    real_test_result = report.classification is None or report.classification in {
        FailureCategory.APPLICATION_CODE_ERROR,
        FailureCategory.GENERATED_TEST_ERROR,
        FailureCategory.TEST_FAILURE,
    }

    if real_test_result and (report.passed_tests or report.failed_tests):
        print()
        print(f"{report.passed_tests} passed")
        print(f"{report.failed_tests} failed")

    if report.classification is not None:
        print()
        print("Classification:")
        print(report.classification.value.upper())

    if report.tester_summary:
        print()
        print("Tester analysis:")
        print(report.tester_summary)

    if report.debug_summary:
        print()
        print("Debugger analysis:")
        print(report.debug_summary)

    print()
    print("Repair attempts:")
    print(report.repair_attempts)

    print()
    print("Terminal reason:")
    print(report.terminal_reason)

    if report.error_message:
        print()
        print("Error:")
        print(report.error_message)

    return EXIT_SUCCESS


def cmd_docs(args: argparse.Namespace) -> int:
    application = Application()

    try:
        state = application.run_service.load_state(args.run_id)
    except (InvalidRunIdError, RunNotFoundError, RunCorruptedError) as error:
        return _report_lookup_error(args.run_id, error)

    docs = state.documentation.generated_docs

    if args.path is None:
        if not docs:
            print("No documentation generated for this run.")
            return EXIT_SUCCESS

        print(f"{'PATH':<40} {'TITLE':<30} {'STATUS':<10}")

        for doc in docs:
            status = "generated" if doc.path in state.documentation.written_files else "failed"
            print(f"{doc.path:<40} {doc.title:<30} {status:<10}")

        return EXIT_SUCCESS

    doc = next((d for d in docs if d.path == args.path), None)

    if doc is None:
        _print_error(f"Documentation file not found in run {args.run_id}: {args.path}")
        return EXIT_INVALID_ARGUMENT

    if args.metadata:
        status = "generated" if doc.path in state.documentation.written_files else "failed"
        print(f"Path: {doc.path}")
        print(f"Title: {doc.title}")
        print(f"Description: {doc.description or '-'}")
        print("Generating agent: documentation")
        print(f"Status: {status}")
        return EXIT_SUCCESS

    if args.output:
        try:
            Path(args.output).write_text(doc.content, encoding="utf-8")
        except OSError as error:
            _print_error(f"Could not write to {args.output}: {error}")
            return EXIT_UNEXPECTED_ERROR

        print(f"Wrote {args.path} to {args.output}")
        return EXIT_SUCCESS

    print(doc.content)

    return EXIT_SUCCESS




def cmd_mcp_list(args: argparse.Namespace) -> int:
    application = Application()
    servers = application.mcp_management_service.list_servers()

    if not servers:
        print("No MCP servers configured.")
        return EXIT_SUCCESS

    print(f"{'ID':<20} {'STATUS':<22} {'TRANSPORT':<10} {'TOOLS':<6} {'AUTH':<14}")

    for server in servers:
        print(
            f"{server.id:<20} {server.connection_status.value:<22} "
            f"{server.transport:<10} {server.tool_count:<6} {server.auth_type:<14}"
        )

    return EXIT_SUCCESS


def cmd_mcp_inspect(args: argparse.Namespace) -> int:
    application = Application()

    try:
        server = application.mcp_management_service.get_server(args.server_name)
    except MCPServerNotFoundError as error:
        _print_error(str(error))
        return EXIT_INVALID_ARGUMENT

    print(f"ID: {server.id}")
    print(f"Display name: {server.display_name}")
    print(f"Description: {server.description or '-'}")
    print(f"Transport: {server.transport}")
    print(f"Remote: {server.is_remote}")
    print(f"Endpoint: {server.endpoint}")
    print(f"Connection status: {server.connection_status.value}")
    print(f"Auth type: {server.auth_type}")
    print(f"Auth configured: {server.auth_configured}")
    print(f"Tool count: {server.tool_count}")
    print(f"Last health check: {server.last_health_check.isoformat() if server.last_health_check else '-'}")
    print(f"Version: {server.version or '-'}")
    print(f"Latency (ms): {server.latency_ms if server.latency_ms is not None else '-'}")

    return EXIT_SUCCESS


def cmd_mcp_tools(args: argparse.Namespace) -> int:
    application = Application()

    if args.server_name:
        try:
            application.mcp_management_service.get_server(args.server_name)
        except MCPServerNotFoundError as error:
            _print_error(str(error))
            return EXIT_INVALID_ARGUMENT

    tools = application.mcp_management_service.list_tools(server_name=args.server_name, query=args.query)

    if not tools:
        print("No tools found.")
        return EXIT_SUCCESS

    print(f"{'IDENTITY':<40} {'SERVER':<16} {'DESCRIPTION':<50}")

    for tool in tools:
        print(f"{tool.identity:<40} {tool.server_name:<16} {tool.description[:50]:<50}")

    return EXIT_SUCCESS


def cmd_mcp_health(args: argparse.Namespace) -> int:
    application = Application()

    if args.server_name:
        try:
            application.mcp_management_service.get_server(args.server_name)
        except MCPServerNotFoundError as error:
            _print_error(str(error))
            return EXIT_INVALID_ARGUMENT

        results = {
            args.server_name: asyncio.run(application.mcp_management_service.check_health(args.server_name))
        }
    else:
        results = asyncio.run(application.mcp_management_service.check_all_health())

    if not results:
        print("No enabled MCP servers to check.")
        return EXIT_SUCCESS

    print(f"{'SERVER':<20} {'STATUS':<22} {'LATENCY (ms)':<14}")

    for name, result in results.items():
        latency = f"{result.latency_ms:.1f}" if result.latency_ms is not None else "-"
        print(f"{name:<20} {result.status.value:<22} {latency:<14}")

    return EXIT_SUCCESS


def cmd_mcp_test(args: argparse.Namespace) -> int:
    application = Application()

    try:
        application.mcp_management_service.get_server(args.server_name)
    except MCPServerNotFoundError as error:
        _print_error(str(error))
        return EXIT_INVALID_ARGUMENT

    result = asyncio.run(application.mcp_management_service.check_health(args.server_name))

    print(f"Status: {result.status.value}")

    if result.latency_ms is not None:
        print(f"Latency: {result.latency_ms:.1f}ms")

    if result.version:
        print(f"Version: {result.version}")

    if result.error:
        print(f"Error: {result.error}")

    return EXIT_SUCCESS if result.status.value == "online" else EXIT_UNEXPECTED_ERROR


def cmd_mcp_refresh(args: argparse.Namespace) -> int:
    application = Application()
    refreshed = asyncio.run(application.mcp_management_service.refresh_registry())

    if not refreshed:
        print("No servers refreshed (none enabled, or all failed to connect).")
        return EXIT_SUCCESS

    print(f"Refreshed: {', '.join(refreshed)}")

    return EXIT_SUCCESS


def cmd_mcp_execute(args: argparse.Namespace) -> int:
    application = Application()

    try:
        arguments = json.loads(args.args) if args.args else {}
    except json.JSONDecodeError as error:
        _print_error(f"--args must be valid JSON: {error}")
        return EXIT_INVALID_ARGUMENT

    if not isinstance(arguments, dict):
        _print_error("--args must be a JSON object.")
        return EXIT_INVALID_ARGUMENT

    try:
        result = application.mcp_tool_executor.execute(
            agent=None,
            tool_identity=args.tool_identity,
            arguments=arguments,
        )
    except AgentForgeException as error:
        _print_error(str(error))
        return EXIT_UNEXPECTED_ERROR

    print(f"Success: {result.success}")

    if result.truncated:
        print("(result truncated)")

    print(result.data or "")

    return EXIT_SUCCESS if result.success else EXIT_UNEXPECTED_ERROR
