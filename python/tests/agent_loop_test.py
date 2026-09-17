"""Contract tests for the observable, bounded agent loop.

These pin the behaviour the loop exists to provide: a deterministic event
order around every model call, message counts that make context growth
visible, termination at each configured bound, and denial/error outcomes that
stay auditable instead of being retried away.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from pedro_agentware.executor.agent_loop import (
    AgentLoop,
    AgentLoopConfig,
    AgentTerminationReason,
    categorize_error,
)
from pedro_agentware.llm import Message
from pedro_agentware.llm.request import Role
from pedro_agentware.llm.response import Response, TokenUsage
from pedro_agentware.llm.response import ToolCall as LLMToolCall
from pedro_agentware.middleware import (
    Action,
    AuditFilter,
    CallerContext,
    InMemoryAuditor,
    MiddlewareImpl,
)
from pedro_agentware.middleware.guardrails import (
    ErrorTracker,
    ModelCallLimiter,
    ResponseValidator,
    StepEnforcer,
)
from pedro_agentware.middleware.hooks import (
    EventKind,
    LoggingObserver,
    RecordingObserver,
    SafeObserver,
)
from pedro_agentware.middleware.policy import (
    Condition,
    Operator,
    Policy,
    Rule,
    SimplePolicyEvaluator,
)
from pedro_agentware.middleware.types import MessageType


@dataclass
class MockBackend:
    """Backend that replays a fixed script of responses."""

    responses: list[Response]
    calls: list[list[Message]] = field(default_factory=list)
    call_count: int = 0
    raises: Exception | None = None

    def complete(self, messages: list[Message]) -> Response:
        if self.raises is not None:
            raise self.raises
        self.calls.append(list(messages))
        resp = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        return resp

    def supports_native_tool_calling(self) -> bool:
        return True

    def model_name(self) -> str:
        return "mock"

    def context_window_size(self) -> int:
        return 8192


class StubTool:
    """Minimal registry-shaped tool."""

    def __init__(self, name: str = "lookup") -> None:
        self.name = name
        self.description = f"{name} tool"

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"q": {"type": "string"}}}

    def execute(self, args: dict[str, Any]) -> Any:  # pragma: no cover - unused
        return None


class RecordingExecutor:
    """Tool executor that records the caller context it was handed."""

    def __init__(self, result: Any = "ok", success: bool = True, error: str = "") -> None:
        self.result = result
        self.success = success
        self.error = error
        self.seen: list[tuple[str, dict[str, Any], CallerContext, str]] = []

    def execute(
        self,
        tool_name: str,
        args: dict[str, Any],
        caller: CallerContext,
        framework: str = "",
    ) -> tuple[Any, bool, str]:
        self.seen.append((tool_name, args, caller, framework))
        return self.result, self.success, self.error


class RaisingExecutor:
    """Tool executor whose tool blows up."""

    def execute(
        self,
        tool_name: str,
        args: dict[str, Any],
        caller: CallerContext,
        framework: str = "",
    ) -> tuple[Any, bool, str]:
        raise RuntimeError("boom")


def _registry(*names: str):
    from pedro_agentware.tools import ToolRegistry

    registry = ToolRegistry()
    for name in names or ("lookup",):
        registry.register(StubTool(name))
    return registry


def _tool_response(name: str = "lookup", **args: Any) -> Response:
    return Response(
        tool_calls=[LLMToolCall(id="call-1", name=name, arguments=dict(args))],
        finish_reason="tool_calls",
    )


def _loop(backend: MockBackend, **overrides: Any) -> tuple[AgentLoop, RecordingObserver]:
    observer = RecordingObserver()
    config: dict[str, Any] = {
        "backend": backend,
        "registry": _registry(),
        "tool_executor": RecordingExecutor(),
        "validator": ResponseValidator(["lookup"]),
        "observers": [observer],
        "max_iterations": 5,
    }
    config.update(overrides)
    return AgentLoop(AgentLoopConfig(**config)), observer


# --- the demo path: model -> tool call -> tool result -> model -> answer ---


def test_full_round_trip_emits_events_in_deterministic_order() -> None:
    """The canonical run produces exactly the documented event sequence."""
    backend = MockBackend(
        responses=[
            _tool_response(q="pedro"),
            Response(
                content="The answer is 42",
                finish_reason="stop",
                usage_tokens=TokenUsage(total_tokens=30),
            ),
        ]
    )
    loop, observer = _loop(backend)

    result = loop.run("sys", "question", session_id="s1")

    assert result.termination_reason is AgentTerminationReason.COMPLETE
    assert result.final_response == "The answer is 42"
    assert result.iterations == 2
    assert result.model_calls == 2
    assert result.tool_calls_made == 1
    assert result.nudges == 0

    assert observer.kinds() == [
        EventKind.RUN_START,
        EventKind.BEFORE_MODEL,
        EventKind.AFTER_MODEL,
        EventKind.TOOL_CALL,
        EventKind.TOOL_RESULT,
        EventKind.BEFORE_MODEL,
        EventKind.AFTER_MODEL,
        EventKind.FINAL_ANSWER,
        EventKind.RUN_END,
    ]
    # Sequence numbers are dense and monotonic, so ordering assertions never
    # depend on wall-clock time.
    assert [e.sequence for e in observer.events] == list(range(len(observer.events)))


def test_before_model_reports_growing_message_count() -> None:
    """Each before_model line shows the conversation the model is handed."""
    backend = MockBackend(
        responses=[_tool_response(q="a"), Response(content="done", finish_reason="stop")]
    )
    loop, observer = _loop(backend)

    loop.run("sys", "question", session_id="s1")

    before = observer.of_kind(EventKind.BEFORE_MODEL)
    # system + user, then + assistant tool-call turn + tool result.
    assert [e.message_count for e in before] == [2, 4]
    assert [e.data["message_count"] for e in before] == [2, 4]
    assert [e.iteration for e in before] == [1, 2]
    # The count matches what the backend actually received.
    assert [len(c) for c in backend.calls] == [2, 4]


def test_every_model_call_is_bracketed_by_before_and_after() -> None:
    """before_model and after_model always come in balanced pairs."""
    backend = MockBackend(
        responses=[_tool_response(q="a"), _tool_response(q="b"), Response(content="fin")]
    )
    loop, observer = _loop(backend)
    result = loop.run("sys", "q", session_id="s1")

    before = observer.of_kind(EventKind.BEFORE_MODEL)
    after = observer.of_kind(EventKind.AFTER_MODEL)
    assert len(before) == len(after) == result.model_calls == 3
    for b, a in zip(before, after):
        assert b.sequence < a.sequence
        assert b.iteration == a.iteration


def test_assistant_tool_call_turn_is_recorded_before_results() -> None:
    """The model sees what it asked for, not just the answers."""
    backend = MockBackend(
        responses=[_tool_response(q="a"), Response(content="done", finish_reason="stop")]
    )
    loop, _ = _loop(backend)

    result = loop.run("sys", "question", session_id="s1")

    roles = [m.role for m in result.conversation]
    assert roles == [Role.SYSTEM, Role.USER, Role.ASSISTANT, Role.TOOL, Role.ASSISTANT]
    types = [m.meta.type for m in result.conversation]
    assert types == [
        MessageType.SYSTEM_PROMPT,
        MessageType.USER_INPUT,
        MessageType.TOOL_CALL,
        MessageType.TOOL_RESULT,
        MessageType.TEXT_RESPONSE,
    ]
    tool_call_turn = result.conversation[2]
    assert [tc.name for tc in tool_call_turn.tool_calls] == ["lookup"]


def test_system_prompt_leads_history() -> None:
    """Cross-language contract: system prompt ahead of caller history."""
    backend = MockBackend(responses=[Response(content="done", finish_reason="stop")])
    loop, _ = _loop(backend)

    history = [
        Message(role=Role.USER, content="h1"),
        Message(role=Role.ASSISTANT, content="h2"),
    ]
    result = loop.run("sys", "user", history=history, session_id="s1")

    sent = backend.calls[0]
    assert sent[0].role == Role.SYSTEM and sent[0].content == "sys"
    assert [m.content for m in sent[1:3]] == ["h1", "h2"]
    assert sent[-1].content == "user"
    assert result.final_response == "done"


# --- termination at known limits ---


def test_runaway_loop_terminates_at_max_iterations() -> None:
    """A model that only ever calls tools stops at the iteration bound."""
    backend = MockBackend(responses=[_tool_response(q="again")])
    loop, observer = _loop(backend, max_iterations=4)

    result = loop.run("sys", "q", session_id="s1")

    assert result.termination_reason is AgentTerminationReason.MAX_ITERATIONS
    assert result.iterations == 4
    assert result.model_calls == 4
    assert len(observer.of_kind(EventKind.BEFORE_MODEL)) == 4
    assert observer.kinds()[-1] is EventKind.RUN_END


def test_model_call_limiter_is_the_hard_wall() -> None:
    """The limiter stops a runaway loop inside its configured hard limit."""
    backend = MockBackend(responses=[_tool_response(q="again")])
    limiter = ModelCallLimiter(hard_limit=3)
    # max_iterations is deliberately far larger: the limiter, not the
    # iteration bound, is what must stop this run.
    loop, observer = _loop(backend, max_iterations=50, model_call_limiter=limiter)

    result = loop.run("sys", "q", session_id="s1")

    assert result.termination_reason is AgentTerminationReason.MODEL_CALL_LIMIT
    assert result.model_calls == 3
    assert backend.call_count == 3
    assert limiter.calls("s1") == 3

    guardrails = observer.of_kind(EventKind.GUARDRAIL)
    kinds = [g.data.get("guardrail") for g in guardrails]
    assert "model_call_limit" in kinds
    limit_event = next(g for g in guardrails if g.data.get("guardrail") == "model_call_limit")
    assert limit_event.data["calls"] == 3
    assert limit_event.data["hard_limit"] == 3


def test_limiter_defaults_to_max_iterations_so_a_cap_always_exists() -> None:
    """Omitting a limiter must not mean an unbounded run."""
    backend = MockBackend(responses=[_tool_response(q="again")])
    loop, _ = _loop(backend, max_iterations=3)

    assert loop.model_call_limiter.hard_limit == 3
    result = loop.run("sys", "q", session_id="s1")
    assert result.model_calls <= 3


def test_nudges_are_bounded_so_invalid_output_cannot_loop_forever() -> None:
    """A model that never produces a valid call terminates, it does not spin."""
    backend = MockBackend(responses=[Response(content="just prose", finish_reason="stop")])
    loop, observer = _loop(
        backend, max_iterations=50, max_nudges=2, require_tool_call=True
    )

    result = loop.run("sys", "q", session_id="s1")

    assert result.termination_reason is AgentTerminationReason.NUDGES_EXHAUSTED
    assert result.nudges == 2
    assert len(observer.of_kind(EventKind.NUDGE)) == 2
    # Bounded well below max_iterations: the nudge cap is what stopped it.
    assert result.iterations == 3
    exhausted = observer.of_kind(EventKind.GUARDRAIL)[-1]
    assert exhausted.data["guardrail"] == "max_nudges"


def test_nudge_is_surfaced_and_recorded_in_the_conversation() -> None:
    """A nudge is observable and lands in history with its message type."""
    # A hallucinated tool is nudged; the model then calls a real one and the
    # run completes -- the nudge corrected rather than terminated it.
    backend = MockBackend(
        responses=[
            _tool_response("nonexistent"),
            _tool_response("lookup", q="a"),
            Response(content="done", finish_reason="stop"),
        ]
    )
    loop, observer = _loop(backend)

    result = loop.run("sys", "q", session_id="s1")

    assert result.termination_reason is AgentTerminationReason.COMPLETE
    assert result.final_response == "done"
    assert result.nudges == 1
    nudge_events = observer.of_kind(EventKind.NUDGE)
    assert len(nudge_events) == 1
    assert nudge_events[0].data["kind"] == "unknown_tool"
    assert MessageType.RETRY_NUDGE in [m.meta.type for m in result.conversation]


def test_model_error_terminates_with_error_and_balanced_bracket() -> None:
    """A failing model call is observable and does not leave a dangling pair."""
    backend = MockBackend(responses=[], raises=RuntimeError("backend down"))
    tracker = ErrorTracker()
    loop, observer = _loop(backend, error_tracker=tracker)

    result = loop.run("sys", "q", session_id="s1")

    assert result.termination_reason is AgentTerminationReason.ERROR
    assert len(observer.of_kind(EventKind.BEFORE_MODEL)) == 1
    assert len(observer.of_kind(EventKind.AFTER_MODEL)) == 1
    assert "backend down" in observer.of_kind(EventKind.AFTER_MODEL)[0].data["error"]
    assert observer.of_kind(EventKind.ERROR)[0].data["stage"] == "model"
    assert len(tracker.get_recent_errors("s1")) == 1


# --- guardrail interventions ---


def test_step_enforcer_blocks_and_nudges_without_executing() -> None:
    """A tool missing its prerequisite is nudged, not run."""
    backend = MockBackend(
        responses=[_tool_response("submit"), Response(content="done", finish_reason="stop")]
    )
    enforcer = StepEnforcer()
    enforcer.add_step("submit", ["review"])
    executor = RecordingExecutor()
    loop, observer = _loop(
        backend,
        registry=_registry("submit", "review"),
        validator=ResponseValidator(["submit", "review"]),
        step_enforcer=enforcer,
        tool_executor=executor,
    )

    result = loop.run("sys", "q", session_id="s1")

    assert executor.seen == []
    assert result.tool_calls_made == 0
    guardrail = observer.of_kind(EventKind.GUARDRAIL)[0]
    assert guardrail.data["guardrail"] == "step_enforcer"
    assert guardrail.data["missing_steps"] == ["review"]
    assert MessageType.STEP_NUDGE in [m.meta.type for m in result.conversation]


def test_repeatedly_failing_tool_is_blocked_rather_than_retried() -> None:
    """The error tracker cuts off a tool that keeps failing."""
    backend = MockBackend(responses=[_tool_response(q="a")])
    tracker = ErrorTracker(max_errors_per_tool=2)
    executor = RecordingExecutor(success=False, error="upstream exploded")
    loop, observer = _loop(
        backend,
        max_iterations=6,
        error_tracker=tracker,
        tool_executor=executor,
    )

    result = loop.run("sys", "q", session_id="s1")

    # Two real attempts, then the tracker blocks further execution.
    assert len(executor.seen) == 2
    assert result.tool_calls_made == 2
    blocked = [
        g for g in observer.of_kind(EventKind.GUARDRAIL) if g.data.get("guardrail") == "error_tracker"
    ]
    assert blocked, "expected the error tracker to block the failing tool"
    assert any(
        e.data.get("blocked") for e in observer.of_kind(EventKind.TOOL_RESULT)
    )


def test_raising_tool_becomes_an_auditable_failed_result() -> None:
    """A tool that raises must not take down the run."""
    backend = MockBackend(
        responses=[_tool_response(q="a"), Response(content="recovered", finish_reason="stop")]
    )
    tracker = ErrorTracker()
    loop, observer = _loop(backend, tool_executor=RaisingExecutor(), error_tracker=tracker)

    result = loop.run("sys", "q", session_id="s1")

    assert result.termination_reason is AgentTerminationReason.COMPLETE
    failed = observer.of_kind(EventKind.TOOL_RESULT)[0]
    assert failed.data["success"] is False
    assert "boom" in failed.data["error"]
    assert tracker.get_error_count("s1", "lookup") == 1


def test_unknown_tool_is_rejected_by_the_validator() -> None:
    """A hallucinated tool is nudged rather than dispatched."""
    backend = MockBackend(responses=[_tool_response("nonexistent")])
    executor = RecordingExecutor()
    loop, observer = _loop(
        backend, max_iterations=2, max_nudges=1, tool_executor=executor
    )

    result = loop.run("sys", "q", session_id="s1")

    assert executor.seen == []
    assert result.nudges == 1
    assert observer.of_kind(EventKind.NUDGE)[0].data["kind"] == "unknown_tool"


# --- authorization: denial stays denied, and stays auditable ---


def _deny_policy() -> SimplePolicyEvaluator:
    return SimplePolicyEvaluator(
        Policy(
            rules=[
                Rule(
                    name="no-untrusted-lookup",
                    tools=["lookup"],
                    action=Action.DENY,
                    conditions=[
                        Condition(
                            field="caller.trusted",
                            operator=Operator.EQ,
                            value="false",
                        )
                    ],
                )
            ],
        )
    )


def test_policy_denial_is_surfaced_audited_and_not_retried_around() -> None:
    """A denied call fails closed, is audited, and the loop does not evade it."""
    backend = MockBackend(
        responses=[_tool_response(q="secret"), Response(content="ok", finish_reason="stop")]
    )
    auditor = InMemoryAuditor()
    middleware = MiddlewareImpl(
        executor=RecordingExecutor(), evaluator=_deny_policy(), auditor=auditor
    )
    tracker = ErrorTracker()
    loop, observer = _loop(backend, tool_executor=middleware, error_tracker=tracker)

    # trusted defaults to False -- fail closed.
    caller = CallerContext(
        user_id="u1", session_id="s1", invoking_subject="human@example.com"
    )
    result = loop.run("sys", "q", session_id="s1", caller=caller)

    denied = observer.of_kind(EventKind.TOOL_RESULT)[0]
    assert denied.data["success"] is False
    assert "denied by policy" in denied.data["error"]
    assert denied.data["category"] == "permission"

    records = auditor.query(AuditFilter(session_id="s1"))
    assert len(records) == 1
    assert records[0].decision.action is Action.DENY
    assert records[0].invoking_subject == "human@example.com"
    assert records[0].tool_name == "lookup"
    # The denial reached the conversation, so the model is told, not silently
    # looped.
    assert any("denied by policy" in m.content for m in result.conversation)


def test_caller_context_reaches_the_executor_unchanged() -> None:
    """The delegation contract survives the loop."""
    backend = MockBackend(
        responses=[_tool_response(q="a"), Response(content="done", finish_reason="stop")]
    )
    executor = RecordingExecutor()
    loop, _ = _loop(backend, tool_executor=executor, framework="harness-x")

    caller = CallerContext(
        user_id="agent-1",
        session_id="s1",
        invoking_subject="human@example.com",
        parent_span="span-parent",
        delegation_depth=2,
    )
    loop.run("sys", "q", session_id="s1", caller=caller)

    assert len(executor.seen) == 1
    _, _, seen_caller, framework = executor.seen[0]
    assert seen_caller.invoking_subject == "human@example.com"
    assert seen_caller.parent_span == "span-parent"
    assert seen_caller.delegation_depth == 2
    assert seen_caller.trusted is False
    assert framework == "harness-x"


def test_session_id_is_filled_into_a_context_that_lacks_one() -> None:
    """Guardrail state and audit records must agree on the session."""
    backend = MockBackend(
        responses=[_tool_response(q="a"), Response(content="done", finish_reason="stop")]
    )
    executor = RecordingExecutor()
    loop, _ = _loop(backend, tool_executor=executor)

    loop.run("sys", "q", session_id="s1", caller=CallerContext(user_id="u1"))

    assert executor.seen[0][2].session_id == "s1"


# --- observability plumbing ---


def test_a_raising_observer_cannot_break_a_run() -> None:
    """Observation is a diagnostic, never control flow."""

    class Exploding:
        def on_event(self, event: Any) -> None:
            raise RuntimeError("observer down")

    backend = MockBackend(responses=[Response(content="done", finish_reason="stop")])
    good = RecordingObserver()
    loop, _ = _loop(backend, observers=[SafeObserver(Exploding()), good])

    result = loop.run("sys", "q", session_id="s1")

    assert result.termination_reason is AgentTerminationReason.COMPLETE
    assert good.kinds()[0] is EventKind.RUN_START


def test_observers_are_wrapped_safely_by_default() -> None:
    """A bare observer does not need the caller to remember SafeObserver."""

    class Exploding:
        def on_event(self, event: Any) -> None:
            raise RuntimeError("observer down")

    backend = MockBackend(responses=[Response(content="done", finish_reason="stop")])
    loop, _ = _loop(backend, observers=[Exploding()])

    result = loop.run("sys", "q", session_id="s1")
    assert result.termination_reason is AgentTerminationReason.COMPLETE


def test_logging_observer_leads_before_model_with_the_message_count() -> None:
    """The visible line is the one the production demo shows."""
    lines: list[str] = []
    backend = MockBackend(
        responses=[_tool_response(q="a"), Response(content="done", finish_reason="stop")]
    )
    loop, _ = _loop(backend, observers=[LoggingObserver(sink=lines.append)])

    loop.run("sys", "q", session_id="s1")

    before_lines = [ln for ln in lines if "before_model" in ln]
    assert before_lines == [
        "[agent 1] before_model messages=2",
        "[agent 2] before_model messages=4",
    ]
    assert any("run_end" in ln and "reason=complete" in ln for ln in lines)


def test_result_carries_the_full_event_trace() -> None:
    """A caller that registered no observer can still inspect the run."""
    backend = MockBackend(responses=[Response(content="done", finish_reason="stop")])
    loop = AgentLoop(
        AgentLoopConfig(
            backend=backend,
            registry=_registry(),
            tool_executor=RecordingExecutor(),
            validator=ResponseValidator(["lookup"]),
        )
    )

    result = loop.run("sys", "q", session_id="s1")

    assert [e.kind for e in result.events][0] is EventKind.RUN_START
    assert [e.kind for e in result.events][-1] is EventKind.RUN_END
    assert result.events[-1].data["termination_reason"] == "complete"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("request timed out", "timeout"),
        ("unknown tool foo", "not_found"),
        ("invalid args for x", "invalid_args"),
        ("denied by policy: nope", "permission"),
        ("rate limit exceeded", "rate_limit"),
        ("something else", "unknown"),
    ],
)
def test_error_categorization_matches_the_typescript_contract(
    message: str, expected: str
) -> None:
    assert categorize_error(message).value == expected
