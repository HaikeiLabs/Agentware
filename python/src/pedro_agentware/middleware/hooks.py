"""Observability hooks for the agent loop.

The agent loop is a state machine whose interesting moments -- a model call,
a tool call, a nudge, a guardrail intervention, a termination -- are otherwise
invisible to anything outside it. This module gives those moments a name, an
ordering and a payload, so a caller can watch a run without the loop having to
guess how the caller wants to render it.

The contract is deliberately narrow:

* :class:`LoopObserver` has one method. Anything callable-shaped satisfies it,
  including a bare function wrapped in :class:`FunctionObserver`.
* Events are emitted in the order they happen, and every event carries the
  monotonically increasing ``sequence`` it was emitted with, so an assertion on
  ordering does not depend on wall-clock time.
* ``BEFORE_MODEL`` carries ``message_count`` -- the size of the conversation
  the model is about to be handed. This is the number that makes context growth
  and runaway loops legible at a glance.

Observers are diagnostics, never control flow. An observer that raises must not
be able to change what the loop decides or take down a run, so
:meth:`emit` isolates failures: see :class:`SafeObserver`.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

__all__ = [
    "EventKind",
    "FunctionObserver",
    "LoggingObserver",
    "LoopEvent",
    "LoopObserver",
    "RecordingObserver",
    "SafeObserver",
]


class EventKind(str, Enum):
    """The observable moments of a single agent run, in the order they occur.

    ``BEFORE_MODEL`` and ``AFTER_MODEL`` always bracket a model call: an
    ``AFTER_MODEL`` is emitted even when the call raised, with ``error`` set,
    so the pair is never left unbalanced for a consumer counting them.
    """

    RUN_START = "run_start"
    BEFORE_MODEL = "before_model"
    AFTER_MODEL = "after_model"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    NUDGE = "nudge"
    GUARDRAIL = "guardrail"
    ERROR = "error"
    FINAL_ANSWER = "final_answer"
    RUN_END = "run_end"


@dataclass(frozen=True)
class LoopEvent:
    """One observable moment in an agent run.

    Attributes:
        kind: Which moment this is.
        sequence: Monotonic index within the run, starting at 0. Ordering
            assertions should use this rather than timestamps.
        iteration: The 1-based loop iteration the event belongs to. 0 for
            events emitted outside any iteration (``RUN_START``/``RUN_END``).
        session_id: The session this run belongs to.
        message_count: Conversation length at emit time. Set on every event so
            the growth of the conversation is visible across the whole run, not
            only before model calls.
        tool: Tool name, for tool and guardrail events.
        detail: Human-readable one-line summary.
        data: Structured payload; contents depend on ``kind``.
    """

    kind: EventKind
    sequence: int = 0
    iteration: int = 0
    session_id: str = ""
    message_count: int = 0
    tool: str = ""
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class LoopObserver(Protocol):
    """Receives :class:`LoopEvent` values as a run progresses."""

    def on_event(self, event: LoopEvent) -> None:
        """Handle one event. Must not raise; must not block for long."""
        ...


class RecordingObserver:
    """Collects events in order. The observer tests and examples assert against.

    Keeps every event so a test can pin the exact sequence a run produced,
    which is what makes "deterministic order" a checkable property rather than
    a claim.
    """

    def __init__(self) -> None:
        self.events: list[LoopEvent] = []

    def on_event(self, event: LoopEvent) -> None:
        """Append ``event`` to the recorded sequence."""
        self.events.append(event)

    def kinds(self) -> list[EventKind]:
        """Return just the event kinds, in order."""
        return [e.kind for e in self.events]

    def of_kind(self, kind: EventKind) -> list[LoopEvent]:
        """Return the recorded events of a single kind, in order."""
        return [e for e in self.events if e.kind == kind]

    def clear(self) -> None:
        """Drop all recorded events."""
        self.events.clear()


class FunctionObserver:
    """Adapts a plain function into a :class:`LoopObserver`."""

    def __init__(self, fn: Callable[[LoopEvent], None]) -> None:
        self._fn = fn

    def on_event(self, event: LoopEvent) -> None:
        """Forward ``event`` to the wrapped function."""
        self._fn(event)


class LoggingObserver:
    """Writes one line per event, the visible trace of a run.

    The ``before_model`` line leads with the message count, because that is the
    number that shows a conversation growing without bound:

    .. code-block:: text

        [agent 1] before_model messages=3
        [agent 1] after_model  tool_calls=1 finish=tool_calls
        [agent 1] tool_call    lookup args={"q": "pedro"}
        [agent 1] tool_result  lookup ok
        [agent 2] before_model messages=5
        [agent 2] after_model  tool_calls=0 finish=stop
        [agent 2] final_answer len=12
        [agent -] run_end      reason=complete iterations=2 tool_calls=1
    """

    def __init__(
        self,
        log: logging.Logger | None = None,
        level: int = logging.INFO,
        prefix: str = "agent",
        sink: Callable[[str], None] | None = None,
    ) -> None:
        """Build a logging observer.

        Args:
            log: Logger to write to. Defaults to this module's logger.
            level: Level to log each line at.
            prefix: Leading tag for each line.
            sink: Optional plain callable to receive the formatted line
                instead of the logger -- ``print`` for a runnable example, or a
                list's ``append`` for a test that asserts on rendered output.
        """
        self._log = log or logger
        self._level = level
        self._prefix = prefix
        self._sink = sink

    def on_event(self, event: LoopEvent) -> None:
        """Render ``event`` as a single line."""
        line = self.format(event)
        if self._sink is not None:
            self._sink(line)
            return
        self._log.log(self._level, "%s", line)

    def format(self, event: LoopEvent) -> str:
        """Return the one-line rendering of ``event``.

        Exposed so a caller can reuse the format without adopting the sink.
        """
        where = str(event.iteration) if event.iteration else "-"
        head = f"[{self._prefix} {where}] {event.kind.value:<12}"

        if event.kind is EventKind.BEFORE_MODEL:
            return f"{head} messages={event.message_count}"

        body = event.detail
        if event.tool and not body.startswith(event.tool):
            body = f"{event.tool} {body}".strip()
        return f"{head} {body}".rstrip()


class SafeObserver:
    """Wraps an observer so its failures cannot reach the loop.

    Observation is a diagnostic. A broken observer -- one that raises, or a
    logging sink whose file handle has closed -- must degrade to "no trace",
    never to a changed decision or a failed run. Exceptions are swallowed and
    reported once per observer, so a consistently failing observer does not
    itself become a flood of log noise.
    """

    def __init__(self, inner: LoopObserver, log: logging.Logger | None = None) -> None:
        self._inner = inner
        self._log = log or logger
        self._warned = False

    def on_event(self, event: LoopEvent) -> None:
        """Forward ``event``, swallowing and reporting any failure."""
        try:
            self._inner.on_event(event)
        except Exception as exc:  # pragma: no cover - defensive
            if not self._warned:
                self._warned = True
                self._log.warning(
                    "loop observer %r raised on %s and was disabled for this run: %s",
                    type(self._inner).__name__,
                    event.kind.value,
                    exc,
                )
