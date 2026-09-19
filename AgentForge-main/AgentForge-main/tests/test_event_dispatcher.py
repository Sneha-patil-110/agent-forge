from __future__ import annotations

import logging

from backend.events.dispatcher import EventDispatcher
from backend.events.event_types import EventType, WorkflowEvent


def _event(event_type: EventType = EventType.WORKFLOW_STARTED) -> WorkflowEvent:
    return WorkflowEvent(event_type=event_type, run_id="af_20260714_deadbeef")


def test_subscriber_receives_emitted_event() -> None:
    dispatcher = EventDispatcher()
    received = []

    dispatcher.subscribe(received.append)
    dispatcher.emit(_event())

    assert len(received) == 1
    assert received[0].event_type == EventType.WORKFLOW_STARTED


def test_multiple_subscribers_all_receive_event() -> None:
    dispatcher = EventDispatcher()
    first, second = [], []

    dispatcher.subscribe(first.append)
    dispatcher.subscribe(second.append)
    dispatcher.emit(_event())

    assert len(first) == 1
    assert len(second) == 1


def test_unsubscribe_stops_further_delivery() -> None:
    dispatcher = EventDispatcher()
    received = []

    def handler(event: WorkflowEvent) -> None:
        received.append(event)

    dispatcher.subscribe(handler)
    dispatcher.unsubscribe(handler)
    dispatcher.emit(_event())

    assert received == []


def test_events_delivered_in_emission_order() -> None:
    dispatcher = EventDispatcher()
    received = []

    dispatcher.subscribe(received.append)

    dispatcher.emit(_event(EventType.WORKFLOW_STARTED))
    dispatcher.emit(_event(EventType.AGENT_STARTED))
    dispatcher.emit(_event(EventType.AGENT_COMPLETED))

    assert [event.event_type for event in received] == [
        EventType.WORKFLOW_STARTED,
        EventType.AGENT_STARTED,
        EventType.AGENT_COMPLETED,
    ]


def test_failing_subscriber_does_not_prevent_other_subscribers(caplog) -> None:
    dispatcher = EventDispatcher()
    received = []

    def bad_handler(event: WorkflowEvent) -> None:
        raise RuntimeError("subscriber exploded")

    dispatcher.subscribe(bad_handler)
    dispatcher.subscribe(received.append)

    with caplog.at_level(logging.ERROR):
        dispatcher.emit(_event())

    assert len(received) == 1
    assert any("subscriber" in r.message.lower() for r in caplog.records)


def test_failing_subscriber_does_not_raise_out_of_emit() -> None:
    dispatcher = EventDispatcher()

    def bad_handler(event: WorkflowEvent) -> None:
        raise RuntimeError("boom")

    dispatcher.subscribe(bad_handler)

    dispatcher.emit(_event())


def test_dispatcher_instances_do_not_share_subscribers() -> None:
    dispatcher_a = EventDispatcher()
    dispatcher_b = EventDispatcher()
    received_a = []

    dispatcher_a.subscribe(received_a.append)
    dispatcher_b.emit(_event())

    assert received_a == []
