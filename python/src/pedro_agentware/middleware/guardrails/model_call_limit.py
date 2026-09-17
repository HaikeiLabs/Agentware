"""Hard cap on model calls per session.

The loop's ``max_iterations`` bounds *iterations*, which is not the same thing
as bounding *model calls*. An iteration that nudges and retries, or that fans
out over several tool calls, can drive more than one model call, and a loop
that keeps nudging can keep calling the model without its iteration count
telling the whole story. This guardrail counts the thing that actually costs
tokens and latency.

It is deliberately session-scoped and independent of the loop's own counters,
so a runaway loop terminates within a known, configured bound no matter which
path inside the loop is doing the spinning.

``budget`` is a soft warning line, ``hard_limit`` is the wall. Crossing the
budget is reported so a caller can see a run getting expensive; crossing the
hard limit stops it.
"""

from dataclasses import dataclass

__all__ = ["ModelCallLimitError", "ModelCallLimiter", "ModelCallStatus"]


class ModelCallLimitError(RuntimeError):
    """Raised when a session exceeds its hard model-call limit.

    The agent loop terminates on this rather than propagating it, but it is a
    distinct type so a caller driving the limiter directly can catch it.
    """

    def __init__(self, session_id: str, calls: int, hard_limit: int) -> None:
        self.session_id = session_id
        self.calls = calls
        self.hard_limit = hard_limit
        super().__init__(
            f"model call limit exceeded for session {session_id!r}: "
            f"{calls} calls against a hard limit of {hard_limit}"
        )


@dataclass(frozen=True)
class ModelCallStatus:
    """The limiter's view of a session at one moment.

    Attributes:
        calls: Model calls recorded so far.
        budget: The soft warning threshold.
        hard_limit: The wall; at or past this, no further call is allowed.
        over_budget: True once ``calls`` has reached ``budget``.
        exhausted: True once ``calls`` has reached ``hard_limit``.
        remaining: Calls still permitted before the hard limit.
    """

    calls: int
    budget: int
    hard_limit: int
    over_budget: bool
    exhausted: bool
    remaining: int


class ModelCallLimiter:
    """Counts model calls per session and refuses them past a hard limit.

    Usage is check-then-record, mirroring how the loop uses it: ask
    :meth:`check` whether another call is allowed, and call :meth:`record`
    once the call has actually been made.
    """

    def __init__(self, hard_limit: int = 20, budget: int = 0) -> None:
        """Build a limiter.

        Args:
            hard_limit: Maximum model calls per session. Values below 1 are
                clamped to 1: a limiter that permits zero calls could never
                make progress, which is a misconfiguration rather than an
                intent to block everything.
            budget: Soft warning threshold. Defaults to 80% of ``hard_limit``
                (at least 1), which gives a run a chance to be seen going long
                before it is cut off.
        """
        self._hard_limit = max(1, hard_limit)
        if budget > 0:
            self._budget = min(budget, self._hard_limit)
        else:
            self._budget = max(1, int(self._hard_limit * 0.8))
        self._calls: dict[str, int] = {}

    @property
    def hard_limit(self) -> int:
        """The configured hard limit."""
        return self._hard_limit

    @property
    def budget(self) -> int:
        """The configured soft budget."""
        return self._budget

    def calls(self, session_id: str) -> int:
        """Return the model calls recorded for ``session_id``."""
        return self._calls.get(session_id, 0)

    def status(self, session_id: str) -> ModelCallStatus:
        """Return the current :class:`ModelCallStatus` for ``session_id``."""
        calls = self.calls(session_id)
        return ModelCallStatus(
            calls=calls,
            budget=self._budget,
            hard_limit=self._hard_limit,
            over_budget=calls >= self._budget,
            exhausted=calls >= self._hard_limit,
            remaining=max(0, self._hard_limit - calls),
        )

    def check(self, session_id: str) -> ModelCallStatus:
        """Return the status without recording a call.

        ``exhausted`` on the result means the next call must not be made.
        """
        return self.status(session_id)

    def allow(self, session_id: str) -> bool:
        """Return True when another model call is permitted."""
        return not self.status(session_id).exhausted

    def record(self, session_id: str) -> ModelCallStatus:
        """Record one model call against ``session_id`` and return the new status."""
        self._calls[session_id] = self.calls(session_id) + 1
        return self.status(session_id)

    def enforce(self, session_id: str) -> ModelCallStatus:
        """Raise :class:`ModelCallLimitError` when the session is exhausted.

        For callers driving the limiter outside the agent loop, which has its
        own termination path and does not raise.
        """
        status = self.status(session_id)
        if status.exhausted:
            raise ModelCallLimitError(session_id, status.calls, self._hard_limit)
        return status

    def reset_session(self, session_id: str) -> None:
        """Forget the count for ``session_id``."""
        self._calls.pop(session_id, None)
