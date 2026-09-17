"""Tests for the agent-loop observability hooks."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from pedro_agentware.middleware.hooks import (
    EventKind,
    FunctionObserver,
    LoggingObserver,
    LoopEvent,
    LoopObserver,
    RecordingObserver,
    SafeObserver,
)


def test_recording_observer_preserves_order() -> None:
    observer = RecordingObserver()
    observer.on_event(LoopEvent(kind=EventKind.RUN_START, sequence=0))
    observer.on_event(LoopEvent(kind=EventKind.BEFORE_MODEL, sequence=1))
    observer.on_event(LoopEvent(kind=EventKind.RUN_END, sequence=2))

    assert observer.kinds() == [
        EventKind.RUN_START,
        EventKind.BEFORE_MODEL,
        EventKind.RUN_END,
    ]
    assert [e.sequence for e in observer.events] == [0, 1, 2]


def test_of_kind_filters_and_clear_empties() -> None:
    observer = RecordingObserver()
    observer.on_event(LoopEvent(kind=EventKind.BEFORE_MODEL, message_count=2))
    observer.on_event(LoopEvent(kind=EventKind.TOOL_CALL, tool="t"))
    observer.on_event(LoopEvent(kind=EventKind.BEFORE_MODEL, message_count=4))

    before = observer.of_kind(EventKind.BEFORE_MODEL)
    assert [e.message_count for e in before] == [2, 4]

    observer.clear()
    assert observer.events == []


def test_function_observer_adapts_a_plain_callable() -> None:
    seen: list[EventKind] = []
    observer = FunctionObserver(lambda e: seen.append(e.kind))

    observer.on_event(LoopEvent(kind=EventKind.NUDGE))

    assert seen == [EventKind.NUDGE]


def test_logging_observer_leads_before_model_with_message_count() -> None:
    lines: list[str] = []
    observer = LoggingObserver(sink=lines.append)

    observer.on_event(
        LoopEvent(kind=EventKind.BEFORE_MODEL, iteration=3, message_count=7)
    )

    assert lines == ["[agent 3] before_model messages=7"]


def test_logging_observer_renders_tool_events_with_the_tool_name_once() -> None:
    lines: list[str] = []
    observer = LoggingObserver(sink=lines.append)

    observer.on_event(
        LoopEvent(kind=EventKind.TOOL_CALL, iteration=1, tool="lookup", detail='{"q": 1}')
    )
    # A detail that already starts with the tool name must not repeat it.
    observer.on_event(
        LoopEvent(
            kind=EventKind.TOOL_RESULT, iteration=1, tool="lookup", detail="lookup ok"
        )
    )

    assert lines == [
        '[agent 1] tool_call    lookup {"q": 1}',
        "[agent 1] tool_result  lookup ok",
    ]


def test_events_outside_an_iteration_render_a_dash() -> None:
    lines: list[str] = []
    observer = LoggingObserver(sink=lines.append)

    observer.on_event(LoopEvent(kind=EventKind.RUN_END, iteration=0, detail="reason=complete"))

    assert lines == ["[agent -] run_end      reason=complete"]


def test_logging_observer_writes_to_a_logger_when_no_sink(
    caplog: pytest.LogCaptureFixture,
) -> None:
    log = logging.getLogger("test.hooks")
    observer = LoggingObserver(log=log)

    with caplog.at_level(logging.INFO, logger="test.hooks"):
        observer.on_event(LoopEvent(kind=EventKind.BEFORE_MODEL, iteration=1, message_count=2))

    assert "before_model messages=2" in caplog.text


def test_safe_observer_swallows_failures() -> None:
    class Exploding:
        calls = 0

        def on_event(self, event: LoopEvent) -> None:
            Exploding.calls += 1
            raise RuntimeError("down")

    inner = Exploding()
    observer = SafeObserver(inner)

    observer.on_event(LoopEvent(kind=EventKind.RUN_START))
    observer.on_event(LoopEvent(kind=EventKind.RUN_END))

    # Both events were forwarded; neither propagated.
    assert Exploding.calls == 2


def test_recording_observer_satisfies_the_protocol() -> None:
    assert isinstance(RecordingObserver(), LoopObserver)
    assert isinstance(LoggingObserver(), LoopObserver)
