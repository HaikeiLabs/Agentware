#!/usr/bin/env python3
"""Runnable demo of the observable, bounded agent loop.

Run it with no arguments::

    python examples/observable_agent_loop.py

Three scenarios, each printing the loop's event trace as it happens:

1. **Happy path** -- model -> tool call -> tool result -> model -> answer, with
   a ``before_model`` line carrying the message count before every model step.
2. **Runaway** -- a model that never stops calling tools, terminated by the
   model-call limiter at a known hard limit rather than spinning.
3. **Denied** -- a tool call refused by policy: fail-closed, surfaced to the
   model as a failed result, and recorded in the audit log.

No network and no API key: the backend is a scripted stub, so the ordering this
prints is the ordering the tests assert.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pedro_agentware.executor import AgentLoop, AgentLoopConfig
from pedro_agentware.llm import Message
from pedro_agentware.llm.response import Response, TokenUsage
from pedro_agentware.llm.response import ToolCall as LLMToolCall
from pedro_agentware.middleware import (
    Action,
    AuditFilter,
    CallerContext,
    InMemoryAuditor,
    LoggingObserver,
    MiddlewareImpl,
)
from pedro_agentware.middleware.guardrails import ModelCallLimiter, ResponseValidator
from pedro_agentware.middleware.policy import (
    Condition,
    Operator,
    Policy,
    Rule,
    SimplePolicyEvaluator,
)
from pedro_agentware.tools import ToolRegistry


class ScriptedBackend:
    """Replays a fixed list of responses; repeats the last one forever."""

    def __init__(self, responses: list[Response]) -> None:
        self._responses = responses
        self.calls = 0

    def complete(self, messages: list[Message]) -> Response:
        resp = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return resp

    def supports_native_tool_calling(self) -> bool:
        return True

    def model_name(self) -> str:
        return "scripted-demo"

    def context_window_size(self) -> int:
        return 8192


class WeatherTool:
    """A tool that answers a fixed question."""

    name = "get_weather"
    description = "Look up the current weather for a city."

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        }

    def execute(self, args: dict[str, Any]) -> Any:  # pragma: no cover - demo
        return {"city": args.get("city"), "temp_c": 14, "sky": "drizzle"}


class RegistryDispatch:
    """Bottom of the stack: runs the tool the middleware has already allowed."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def execute(self, tool_name: str, args: dict[str, Any]) -> tuple[Any, bool, str]:
        tool, found = self._registry.get(tool_name)
        if not found:
            return None, False, f"unknown tool {tool_name}"
        try:
            return tool.execute(args), True, ""
        except Exception as exc:
            return None, False, str(exc)


def _tool_call(name: str, **args: Any) -> Response:
    return Response(
        tool_calls=[LLMToolCall(id="call-1", name=name, arguments=dict(args))],
        finish_reason="tool_calls",
    )


def _build(backend: ScriptedBackend, **overrides: Any) -> tuple[AgentLoop, InMemoryAuditor]:
    registry = ToolRegistry()
    registry.register(WeatherTool())
    auditor = InMemoryAuditor()

    middleware = MiddlewareImpl(
        executor=RegistryDispatch(registry),
        evaluator=overrides.pop("evaluator", None),
        auditor=auditor,
    )

    config: dict[str, Any] = {
        "backend": backend,
        "registry": registry,
        "tool_executor": middleware,
        "validator": ResponseValidator(registry.names()),
        "observers": [LoggingObserver(sink=print)],
        "max_iterations": 8,
        "framework": "observable-demo",
    }
    config.update(overrides)
    return AgentLoop(AgentLoopConfig(**config)), auditor


def banner(title: str) -> None:
    print(f"\n{'=' * 68}\n{title}\n{'=' * 68}")


def scenario_happy_path() -> None:
    """model -> tool call -> tool result -> model -> answer."""
    banner("1. Happy path: model -> tool -> result -> model -> answer")

    backend = ScriptedBackend(
        [
            _tool_call("get_weather", city="Denver"),
            Response(
                content="It's 14C and drizzling in Denver.",
                finish_reason="stop",
                usage_tokens=TokenUsage(prompt_tokens=120, completion_tokens=14, total_tokens=134),
            ),
        ]
    )
    loop, _ = _build(backend)

    result = loop.run(
        system_prompt="You are a weather assistant.",
        user_message="What's the weather in Denver?",
        session_id="demo-happy",
        caller=CallerContext(
            user_id="agent-1",
            session_id="demo-happy",
            invoking_subject="human@example.com",
        ),
    )

    print(
        f"\n  -> {result.termination_reason.value}: {result.final_response!r}\n"
        f"     iterations={result.iterations} model_calls={result.model_calls} "
        f"tool_calls={result.tool_calls_made} nudges={result.nudges}"
    )
    print(f"     message counts before each model call: "
          f"{[e.message_count for e in result.events if e.kind.value == 'before_model']}")


def scenario_runaway() -> None:
    """A model that never stops, stopped at a known hard limit."""
    banner("2. Runaway: terminated by the model-call limiter at a hard limit")

    backend = ScriptedBackend([_tool_call("get_weather", city="Denver")])
    limiter = ModelCallLimiter(hard_limit=4)
    # max_iterations is far larger on purpose: the limiter is the wall here.
    loop, _ = _build(backend, max_iterations=100, model_call_limiter=limiter)

    result = loop.run(
        system_prompt="You are a weather assistant.",
        user_message="Keep checking forever.",
        session_id="demo-runaway",
    )

    print(
        f"\n  -> {result.termination_reason.value} after "
        f"{result.model_calls} model calls (hard limit {limiter.hard_limit}, "
        f"max_iterations was 100)"
    )
    assert result.model_calls == limiter.hard_limit, "limiter must be the binding constraint"


def scenario_denied() -> None:
    """A policy denial: fail closed, surfaced, and audited."""
    banner("3. Denied: fail-closed policy, surfaced to the model and audited")

    policy = Policy(
        rules=[
            Rule(
                name="untrusted-callers-may-not-read-weather",
                tools=["get_weather"],
                action=Action.DENY,
                conditions=[
                    Condition(
                        field="caller.trusted", operator=Operator.EQ, value="false"
                    )
                ],
            )
        ]
    )

    backend = ScriptedBackend(
        [
            _tool_call("get_weather", city="Denver"),
            Response(content="I'm not allowed to look that up.", finish_reason="stop"),
        ]
    )
    loop, auditor = _build(backend, evaluator=SimplePolicyEvaluator(policy))

    # trusted defaults to False -- a missing caller context is never promoted.
    result = loop.run(
        system_prompt="You are a weather assistant.",
        user_message="What's the weather in Denver?",
        session_id="demo-denied",
        caller=CallerContext(
            user_id="agent-1",
            session_id="demo-denied",
            invoking_subject="human@example.com",
        ),
    )

    records = auditor.query(AuditFilter(session_id="demo-denied"))
    print(f"\n  -> {result.termination_reason.value}: {result.final_response!r}")
    print(f"     audit records: {len(records)}")
    for record in records:
        print(
            f"       {record.tool_name}: {record.decision.action.value} "
            f"(rule={record.decision.rule!r}, "
            f"invoking_subject={record.invoking_subject!r})"
        )
    assert records and records[0].decision.action is Action.DENY, "denial must be audited"


def main() -> None:
    scenario_happy_path()
    scenario_runaway()
    scenario_denied()
    print("\nAll scenarios completed.\n")


if __name__ == "__main__":
    main()
