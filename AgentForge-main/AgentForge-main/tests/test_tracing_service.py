
from __future__ import annotations

import pytest

from backend.mcp import executor as mcp_executor_module
from backend.services import tracing_service as tracing_service_module
from backend.services.tracing_service import TracingService


class _FakeRunTree:
    def __init__(self) -> None:
        self.ended_with: dict | None = None
        self.ended_with_error: str | None = None

    def end(self, *, outputs=None, error=None):
        self.ended_with = outputs
        self.ended_with_error = error


class _FakeSpan:

    instances: list["_FakeSpan"] = []

    def __init__(self, name, **kwargs) -> None:
        self.name = name
        self.kwargs = kwargs
        self.run = _FakeRunTree()
        self.exit_args: tuple | None = None
        _FakeSpan.instances.append(self)

    def __enter__(self):
        return self.run

    def __exit__(self, exc_type, exc_value, tb):
        self.exit_args = (exc_type, exc_value, tb)
        return False


class _RaisingSpan:
    def __init__(self, *args, **kwargs) -> None:
        raise RuntimeError("langsmith is unreachable")


@pytest.fixture(autouse=True)
def _reset_fake_span():
    _FakeSpan.instances.clear()
    yield
    _FakeSpan.instances.clear()


def _configure(monkeypatch, *, tracing: bool, api_key: str | None) -> None:
    monkeypatch.setattr(tracing_service_module.settings, "LANGSMITH_TRACING", tracing)
    monkeypatch.setattr(tracing_service_module.settings, "LANGSMITH_API_KEY", api_key)


def _enabled_service(monkeypatch) -> TracingService:
    _configure(monkeypatch, tracing=True, api_key="test-key")
    monkeypatch.setattr(tracing_service_module, "Client", lambda **kwargs: object())
    monkeypatch.setattr(tracing_service_module, "ls_trace", _FakeSpan)
    monkeypatch.setattr(
        mcp_executor_module, "get_current_run_id", lambda: "af_20260716_deadbeef"
    )
    return TracingService()




def test_disabled_when_langsmith_tracing_is_false(monkeypatch) -> None:
    _configure(monkeypatch, tracing=False, api_key="test-key")

    assert TracingService().enabled is False


def test_disabled_when_api_key_missing(monkeypatch) -> None:
    _configure(monkeypatch, tracing=True, api_key=None)

    assert TracingService().enabled is False


def test_client_construction_failure_disables_tracing_without_raising(monkeypatch) -> None:
    _configure(monkeypatch, tracing=True, api_key="test-key")

    def _raise(**kwargs):
        raise RuntimeError("bad endpoint")

    monkeypatch.setattr(tracing_service_module, "Client", _raise)

    assert TracingService().enabled is False


def test_enabled_when_configured_correctly(monkeypatch) -> None:
    _configure(monkeypatch, tracing=True, api_key="test-key")
    monkeypatch.setattr(tracing_service_module, "Client", lambda **kwargs: object())

    assert TracingService().enabled is True


def test_disabled_factory_never_touches_settings_or_client(monkeypatch) -> None:
    def _boom(**kwargs):
        raise AssertionError("Client must not be constructed for a disabled() instance")

    monkeypatch.setattr(tracing_service_module, "Client", _boom)
    _configure(monkeypatch, tracing=True, api_key="test-key")

    service = TracingService.disabled()

    assert service.enabled is False




def test_trace_disabled_yields_none_and_never_calls_langsmith(monkeypatch) -> None:
    _configure(monkeypatch, tracing=False, api_key=None)
    monkeypatch.setattr(tracing_service_module, "ls_trace", _FakeSpan)

    service = TracingService()

    with service.trace("workflow") as run:
        assert run is None

    assert _FakeSpan.instances == []


def test_trace_enabled_yields_run_and_injects_current_run_id(monkeypatch) -> None:
    service = _enabled_service(monkeypatch)

    with service.trace("workflow", metadata={"agent": "analysis"}) as run:
        assert run is not None

    span = _FakeSpan.instances[0]
    assert span.kwargs["metadata"]["run_id"] == "af_20260716_deadbeef"
    assert span.kwargs["metadata"]["agent"] == "analysis"
    assert span.exit_args == (None, None, None)


def test_trace_records_error_but_does_not_swallow_it(monkeypatch) -> None:
    service = _enabled_service(monkeypatch)

    with pytest.raises(ValueError, match="developer blew up"):
        with service.trace("developer"):
            raise ValueError("developer blew up")

    span = _FakeSpan.instances[0]
    assert span.exit_args[0] is ValueError


def test_trace_setup_failure_falls_back_to_untraced_execution(monkeypatch) -> None:
    _configure(monkeypatch, tracing=True, api_key="test-key")
    monkeypatch.setattr(tracing_service_module, "Client", lambda **kwargs: object())
    monkeypatch.setattr(tracing_service_module, "ls_trace", _RaisingSpan)

    service = TracingService()
    executed = False

    with service.trace("workflow") as run:
        executed = True
        assert run is None

    assert executed is True




def test_set_outputs_is_noop_when_run_is_none() -> None:
    TracingService.set_outputs(None, {"a": 1})


def test_set_outputs_calls_end_on_the_run(monkeypatch) -> None:
    service = _enabled_service(monkeypatch)

    with service.trace("workflow") as run:
        TracingService.set_outputs(run, {"status": "ok"})

    assert run.ended_with == {"status": "ok"}




def test_shutdown_safe_when_disabled(monkeypatch) -> None:
    _configure(monkeypatch, tracing=False, api_key=None)
    service = TracingService()

    service.shutdown()
    service.shutdown()


def test_shutdown_closes_client_and_is_idempotent(monkeypatch) -> None:
    closed: list[float | None] = []

    class _FakeClient:
        def close(self, timeout=None):
            closed.append(timeout)

    _configure(monkeypatch, tracing=True, api_key="test-key")
    monkeypatch.setattr(tracing_service_module, "Client", lambda **kwargs: _FakeClient())

    service = TracingService()
    service.shutdown()
    service.shutdown()

    assert closed == [5.0]
    assert service.enabled is False


def test_shutdown_swallows_close_errors(monkeypatch) -> None:
    class _FakeClient:
        def close(self, timeout=None):
            raise RuntimeError("network down")

    _configure(monkeypatch, tracing=True, api_key="test-key")
    monkeypatch.setattr(tracing_service_module, "Client", lambda **kwargs: _FakeClient())

    service = TracingService()
    service.shutdown()




def test_nested_trace_calls_link_parent_run_ids_via_real_langsmith(monkeypatch) -> None:

    from langsmith.run_trees import RunTree

    created: list[RunTree] = []
    monkeypatch.setattr(RunTree, "post", lambda self, **kwargs: created.append(self))
    monkeypatch.setattr(RunTree, "patch", lambda self, **kwargs: None)

    _configure(monkeypatch, tracing=True, api_key="test-key")
    monkeypatch.setattr(
        mcp_executor_module, "get_current_run_id", lambda: "af_20260716_deadbeef"
    )

    service = TracingService()
    assert service.enabled is True

    with service.trace("workflow", run_type="chain"):
        with service.trace("developer", run_type="chain"):
            with service.trace("llm:developer", run_type="llm"):
                pass

    assert len(created) == 3
    workflow_run, agent_run, llm_run = created

    assert workflow_run.parent_run_id is None
    assert agent_run.parent_run_id == workflow_run.id
    assert llm_run.parent_run_id == agent_run.id