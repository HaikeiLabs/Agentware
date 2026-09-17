"""Observable agent loop: model -> tool call -> tool result -> model -> answer.

Python counterpart to ``typescript/src/executor/agent_loop.ts``, and the loop
the rest of this package's guardrails were written for. It differs from
:class:`~pedro_agentware.executor.executor.InferenceExecutor` in three ways
that matter:

**It is observable.** Every model call is bracketed by ``BEFORE_MODEL`` /
``AFTER_MODEL`` events, and tool calls, tool results, nudges, guardrail
interventions, errors and the final answer are emitted in the order they
happen. ``BEFORE_MODEL`` carries the conversation's message count, so a run
that is growing without bound shows it on every line.

**It terminates.** ``max_iterations`` bounds iterations, ``max_nudges`` bounds
correction attempts so a model that keeps producing invalid output cannot be
nudged forever, and a :class:`ModelCallLimiter` puts a hard wall on model calls
per session regardless of which path inside the loop is spinning. Each of the
three has its own termination reason, so "why did this stop" is answerable from
the result alone.

**It records the assistant's turn.** The model's own tool-call turn is appended
to the conversation before the results are, so the history it sees on the next
call actually contains what it asked for.

Authorization is unchanged and deliberately so: tool calls go through the
injected ``tool_executor``, which is expected to be a
:class:`~pedro_agentware.middleware.middleware.MiddlewareImpl` (or the KEI
equivalent). The loop passes the run's :class:`CallerContext` through on every
call and never inspects, substitutes or upgrades a decision, so fail-closed
policy and the audit trail behave exactly as they do outside the loop. A denial
comes back as a failed tool result, is recorded by the error tracker and is
surfaced as an event -- observable, and still denied.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from ..llm import Message
from ..llm.request import Role, ToolDefinition
from ..llm.response import Response
from ..middleware.guardrails.error_tracker import ErrorCategory, ErrorTracker
from ..middleware.guardrails.model_call_limit import ModelCallLimiter
from ..middleware.guardrails.nudge import Nudge, NudgeKind, step_nudge
from ..middleware.guardrails.response_validator import (
    ResponseValidator,
    ToolCall,
    ValidationResult,
)
from ..middleware.guardrails.step_enforcer import StepEnforcer
from ..middleware.hooks import EventKind, LoopEvent, LoopObserver, SafeObserver
from ..middleware.types import CallerContext, MessageMeta, MessageType
from ..tools import ToolRegistry

__all__ = [
    "AgentLoop",
    "AgentLoopConfig",
    "AgentResult",
    "AgentTerminationReason",
    "LoopToolExecutor",
    "categorize_error",
]


class AgentTerminationReason(str, Enum):
    """Why the loop stopped.

    Every bound the loop enforces gets its own reason: a run that hit a wall
    should never be indistinguishable from one that finished.
    """

    COMPLETE = "complete"
    MAX_ITERATIONS = "max_iterations"
    NUDGES_EXHAUSTED = "nudges_exhausted"
    MODEL_CALL_LIMIT = "model_call_limit"
    ERROR = "error"


class LoopToolExecutor(Protocol):
    """The tool-execution surface the loop needs.

    Matches :class:`~pedro_agentware.middleware.middleware.MiddlewareImpl`, so
    the policy-enforcing middleware drops in unchanged and every tool call the
    loop makes is evaluated and audited.
    """

    def execute(
        self,
        tool_name: str,
        args: dict[str, Any],
        caller: CallerContext,
        framework: str = "",
    ) -> tuple[Any, bool, str]:
        """Execute a tool call. Returns ``(result, success, error)``."""
        ...


@dataclass
class AgentLoopConfig:
    """Configuration for :class:`AgentLoop`.

    Attributes:
        backend: The LLM backend.
        registry: Tool registry, used to advertise tool definitions.
        tool_executor: Policy-enforcing executor; see :class:`LoopToolExecutor`.
        validator: Validates responses and rescues tool calls from text.
        error_tracker: Records tool failures and blocks tools that keep failing.
        step_enforcer: Enforces prerequisite ordering between tools.
        model_call_limiter: Hard cap on model calls per session. One is created
            from ``max_iterations`` when not supplied, so the cap always exists.
        observers: Receive the run's events in order.
        max_iterations: Bound on loop iterations.
        max_nudges: Bound on correction attempts across the whole run.
        require_tool_call: When True, a text answer that yields no tool call is
            treated as invalid and nudged instead of accepted as final.
        framework: Passed to the tool executor for the audit record.
    """

    backend: Any
    registry: ToolRegistry = field(default_factory=ToolRegistry)
    tool_executor: LoopToolExecutor | None = None
    validator: ResponseValidator | None = None
    error_tracker: ErrorTracker | None = None
    step_enforcer: StepEnforcer | None = None
    model_call_limiter: ModelCallLimiter | None = None
    observers: list[LoopObserver] = field(default_factory=list)
    max_iterations: int = 20
    max_nudges: int = 3
    require_tool_call: bool = False
    framework: str = "pedro-agentware"


@dataclass
class AgentResult:
    """Outcome of one agent run.

    ``model_calls`` is reported alongside ``iterations`` because they are not
    the same number -- a nudged iteration costs a model call without advancing
    the conversation -- and the difference is what makes a spinning loop
    visible in the result.
    """

    final_response: str
    iterations: int
    model_calls: int
    tool_calls_made: int
    nudges: int
    termination_reason: AgentTerminationReason
    conversation: list[Message]
    events: list[LoopEvent] = field(default_factory=list)


def categorize_error(message: str) -> ErrorCategory:
    """Classify a tool error message. Mirrors the TypeScript ``categorizeError``."""
    m = message.lower()
    if "timeout" in m or "timed out" in m:
        return ErrorCategory.TIMEOUT
    if "not found" in m or "unknown tool" in m:
        return ErrorCategory.NOT_FOUND
    if "invalid arg" in m or "schema" in m or "validation" in m:
        return ErrorCategory.INVALID_ARGS
    if "permission" in m or "denied" in m or "forbidden" in m:
        return ErrorCategory.PERMISSION
    if "rate limit" in m or "rate_limit" in m:
        return ErrorCategory.RATE_LIMIT
    return ErrorCategory.UNKNOWN


def _nudge_meta_type(kind: NudgeKind) -> MessageType:
    """Map a nudge kind onto the message type it is recorded as."""
    if kind is NudgeKind.STEP:
        return MessageType.STEP_NUDGE
    if kind is NudgeKind.PREREQUISITE:
        return MessageType.PREREQUISITE_NUDGE
    return MessageType.RETRY_NUDGE


def _render(value: Any) -> str:
    """Render a tool result for the conversation, readably and without raising."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def registry_tool_definitions(registry: ToolRegistry) -> list[ToolDefinition]:
    """Build tool definitions from ``registry``."""
    definitions: list[ToolDefinition] = []
    for tool in registry.all():
        schema: dict[str, Any] = {}
        getter = getattr(tool, "input_schema", None)
        if callable(getter):
            try:
                schema = getter()
            except Exception:  # pragma: no cover - defensive
                schema = {}
        definitions.append(
            ToolDefinition(
                name=tool.name,
                description=getattr(tool, "description", ""),
                input_schema=schema,
            )
        )
    return definitions


class AgentLoop:
    """Runs the observable, bounded agent loop."""

    def __init__(self, config: AgentLoopConfig) -> None:
        self._config = config
        self._max_iterations = config.max_iterations if config.max_iterations > 0 else 20
        self._max_nudges = config.max_nudges if config.max_nudges > 0 else 3
        # A limiter always exists. Deriving it from max_iterations when the
        # caller did not supply one means the hard wall is never accidentally
        # absent, and a loop whose iterations each cost one model call is
        # unaffected by it.
        self._limiter = config.model_call_limiter or ModelCallLimiter(
            hard_limit=self._max_iterations
        )
        self._observers = [
            obs if isinstance(obs, SafeObserver) else SafeObserver(obs)
            for obs in config.observers
        ]

    @property
    def model_call_limiter(self) -> ModelCallLimiter:
        """The limiter enforcing this loop's hard model-call cap."""
        return self._limiter

    def run(
        self,
        system_prompt: str,
        user_message: str,
        history: list[Message] | None = None,
        session_id: str = "",
        caller: CallerContext | None = None,
    ) -> AgentResult:
        """Run the loop to a terminal state.

        Args:
            system_prompt: The agent's instructions.
            user_message: The task.
            history: Prior conversation, inserted after the system prompt.
            session_id: Scopes the guardrails and the model-call limiter.
            caller: Delegation context passed to the tool executor on every
                call. A default is built when omitted; ``session_id`` is filled
                in from the argument when the context does not carry one, so
                audit records and guardrail state agree on the session.

        Returns:
            The :class:`AgentResult`, including the full ordered event trace.
        """
        # Cross-language contract: the system prompt leads the conversation,
        # ahead of any caller-supplied history (mirrors Go buildConversation).
        conversation: list[Message] = [
            Message(
                role=Role.SYSTEM,
                content=system_prompt,
                meta=MessageMeta(type=MessageType.SYSTEM_PROMPT),
            )
        ]
        conversation.extend(history or [])
        conversation.append(
            Message(
                role=Role.USER,
                content=user_message,
                meta=MessageMeta(type=MessageType.USER_INPUT),
            )
        )

        caller_ctx = caller or CallerContext(session_id=session_id)
        if not caller_ctx.session_id and session_id:
            caller_ctx = CallerContext(**{**caller_ctx.__dict__, "session_id": session_id})

        tool_defs = registry_tool_definitions(self._config.registry)
        events: list[LoopEvent] = []
        sequence = 0

        def emit(
            kind: EventKind,
            iteration: int,
            *,
            tool: str = "",
            detail: str = "",
            data: dict[str, Any] | None = None,
        ) -> None:
            nonlocal sequence
            event = LoopEvent(
                kind=kind,
                sequence=sequence,
                iteration=iteration,
                session_id=session_id,
                message_count=len(conversation),
                tool=tool,
                detail=detail,
                data=data or {},
            )
            sequence += 1
            events.append(event)
            for observer in self._observers:
                observer.on_event(event)

        iterations = 0
        model_calls = 0
        tool_calls_made = 0
        nudges = 0
        final_response = ""

        emit(
            EventKind.RUN_START,
            0,
            detail=f"tools={len(tool_defs)} max_iterations={self._max_iterations}",
            data={
                "max_iterations": self._max_iterations,
                "max_nudges": self._max_nudges,
                "model_call_hard_limit": self._limiter.hard_limit,
                "tools": [d.name for d in tool_defs],
            },
        )

        def finish(reason: AgentTerminationReason, answer: str) -> AgentResult:
            emit(
                EventKind.RUN_END,
                0,
                detail=(
                    f"reason={reason.value} iterations={iterations} "
                    f"model_calls={model_calls} tool_calls={tool_calls_made} nudges={nudges}"
                ),
                data={
                    "termination_reason": reason.value,
                    "iterations": iterations,
                    "model_calls": model_calls,
                    "tool_calls_made": tool_calls_made,
                    "nudges": nudges,
                },
            )
            return AgentResult(
                final_response=answer,
                iterations=iterations,
                model_calls=model_calls,
                tool_calls_made=tool_calls_made,
                nudges=nudges,
                termination_reason=reason,
                conversation=conversation,
                events=events,
            )

        while iterations < self._max_iterations:
            # The hard wall is checked before the call, not after, so the
            # limit is a bound on calls made rather than on calls survived.
            limit_status = self._limiter.check(caller_ctx.session_id or session_id)
            if limit_status.exhausted:
                emit(
                    EventKind.GUARDRAIL,
                    iterations + 1,
                    detail=(
                        f"model call limit reached: {limit_status.calls}/"
                        f"{limit_status.hard_limit}"
                    ),
                    data={
                        "guardrail": "model_call_limit",
                        "calls": limit_status.calls,
                        "hard_limit": limit_status.hard_limit,
                    },
                )
                return finish(AgentTerminationReason.MODEL_CALL_LIMIT, final_response)

            iterations += 1

            emit(
                EventKind.BEFORE_MODEL,
                iterations,
                detail=f"messages={len(conversation)}",
                data={
                    "message_count": len(conversation),
                    "model_calls_so_far": model_calls,
                    "model_calls_remaining": limit_status.remaining,
                },
            )

            try:
                resp = self._complete(conversation, tool_defs)
            except Exception as exc:
                model_calls += 1
                self._limiter.record(caller_ctx.session_id or session_id)
                # AFTER_MODEL is emitted even on failure so the bracket around
                # a model call is never left unbalanced.
                emit(
                    EventKind.AFTER_MODEL,
                    iterations,
                    detail=f"error={exc}",
                    data={"error": str(exc)},
                )
                if self._config.error_tracker is not None:
                    self._config.error_tracker.record_error(
                        session_id, "", {}, exc, ErrorCategory.UNKNOWN
                    )
                emit(
                    EventKind.ERROR,
                    iterations,
                    detail=f"model call failed: {exc}",
                    data={"error": str(exc), "stage": "model"},
                )
                return finish(AgentTerminationReason.ERROR, final_response)

            model_calls += 1
            status = self._limiter.record(caller_ctx.session_id or session_id)
            emit(
                EventKind.AFTER_MODEL,
                iterations,
                detail=(
                    f"tool_calls={len(resp.tool_calls)} "
                    f"finish={resp.finish_reason or 'stop'} "
                    f"tokens={resp.usage_tokens.total_tokens}"
                ),
                data={
                    "tool_calls": len(resp.tool_calls),
                    "finish_reason": resp.finish_reason,
                    "total_tokens": resp.usage_tokens.total_tokens,
                    "model_calls": model_calls,
                },
            )
            if status.over_budget and not status.exhausted:
                emit(
                    EventKind.GUARDRAIL,
                    iterations,
                    detail=(
                        f"model call budget passed: {status.calls}/{status.budget} "
                        f"(hard limit {status.hard_limit})"
                    ),
                    data={
                        "guardrail": "model_call_budget",
                        "calls": status.calls,
                        "budget": status.budget,
                        "hard_limit": status.hard_limit,
                    },
                )

            validation = self._validate(resp)

            if validation.needs_retry:
                if nudges >= self._max_nudges:
                    # Nudging is bounded: an invalid model that cannot be
                    # corrected terminates the run rather than looping forever.
                    emit(
                        EventKind.GUARDRAIL,
                        iterations,
                        detail=f"nudges exhausted after {nudges}",
                        data={"guardrail": "max_nudges", "nudges": nudges},
                    )
                    return finish(AgentTerminationReason.NUDGES_EXHAUSTED, resp.content)
                nudges += 1
                conversation.append(
                    Message(
                        role=Role.ASSISTANT,
                        content=resp.content,
                        meta=MessageMeta(type=MessageType.TEXT_RESPONSE),
                    )
                )
                if validation.nudge is not None:
                    self._append_nudge(conversation, validation.nudge)
                    emit(
                        EventKind.NUDGE,
                        iterations,
                        detail=validation.nudge.content,
                        data={
                            "kind": validation.nudge.kind.value,
                            "tier": validation.nudge.tier,
                            "nudges": nudges,
                        },
                    )
                continue

            if not validation.tool_calls:
                final_response = resp.content
                emit(
                    EventKind.FINAL_ANSWER,
                    iterations,
                    detail=f"len={len(final_response)}",
                    data={"content": final_response},
                )
                conversation.append(
                    Message(
                        role=Role.ASSISTANT,
                        content=final_response,
                        meta=MessageMeta(type=MessageType.TEXT_RESPONSE),
                    )
                )
                return finish(AgentTerminationReason.COMPLETE, final_response)

            # Record the assistant's own tool-call turn before its results, so
            # the next model call sees what it asked for and not just answers.
            conversation.append(
                Message(
                    role=Role.ASSISTANT,
                    content=resp.content,
                    tool_calls=list(resp.tool_calls),
                    meta=MessageMeta(type=MessageType.TOOL_CALL),
                )
            )

            step_nudged = False

            for call in validation.tool_calls:
                if self._config.step_enforcer is not None:
                    allowed, missing = self._config.step_enforcer.can_execute(
                        session_id, call.tool
                    )
                    if not allowed:
                        if nudges >= self._max_nudges:
                            emit(
                                EventKind.GUARDRAIL,
                                iterations,
                                tool=call.tool,
                                detail=f"nudges exhausted after {nudges}",
                                data={"guardrail": "max_nudges", "nudges": nudges},
                            )
                            return finish(
                                AgentTerminationReason.NUDGES_EXHAUSTED, resp.content
                            )
                        nudges += 1
                        step_nudged = True
                        nudge = step_nudge(call.tool, missing, min(3, nudges))
                        emit(
                            EventKind.GUARDRAIL,
                            iterations,
                            tool=call.tool,
                            detail=f"step enforcer blocked {call.tool}; missing {missing}",
                            data={
                                "guardrail": "step_enforcer",
                                "missing_steps": missing,
                            },
                        )
                        self._append_nudge(conversation, nudge)
                        emit(
                            EventKind.NUDGE,
                            iterations,
                            tool=call.tool,
                            detail=nudge.content,
                            data={
                                "kind": nudge.kind.value,
                                "tier": nudge.tier,
                                "nudges": nudges,
                            },
                        )
                        continue

                if self._config.error_tracker is not None and (
                    self._config.error_tracker.should_block_tool(session_id, call.tool)
                ):
                    # A tool that keeps failing is cut off rather than retried
                    # indefinitely; the block is surfaced and recorded.
                    emit(
                        EventKind.GUARDRAIL,
                        iterations,
                        tool=call.tool,
                        detail=f"{call.tool} blocked after repeated errors",
                        data={"guardrail": "error_tracker"},
                    )
                    self._append_tool_message(
                        conversation,
                        call.tool,
                        f"Tool {call.tool} error: blocked after repeated errors",
                    )
                    emit(
                        EventKind.TOOL_RESULT,
                        iterations,
                        tool=call.tool,
                        detail="blocked after repeated errors",
                        data={"success": False, "blocked": True},
                    )
                    continue

                tool_calls_made += 1
                emit(
                    EventKind.TOOL_CALL,
                    iterations,
                    tool=call.tool,
                    detail=_render(call.args),
                    data={"args": call.args},
                )

                value, success, error = self._execute_tool(call, caller_ctx)

                if success:
                    if self._config.step_enforcer is not None:
                        self._config.step_enforcer.mark_step_complete(session_id, call.tool)
                    rendered = _render(value)
                    self._append_tool_message(
                        conversation, call.tool, f"Tool {call.tool} result: {rendered}"
                    )
                    emit(
                        EventKind.TOOL_RESULT,
                        iterations,
                        tool=call.tool,
                        detail=rendered,
                        data={"success": True, "result": value},
                    )
                else:
                    message = error or "tool failed"
                    if self._config.error_tracker is not None:
                        self._config.error_tracker.record_error(
                            session_id,
                            call.tool,
                            call.args,
                            Exception(message),
                            categorize_error(message),
                        )
                    self._append_tool_message(
                        conversation, call.tool, f"Tool {call.tool} error: {message}"
                    )
                    # A policy denial lands here: surfaced as an observable
                    # failed result, recorded by the error tracker, and still
                    # denied. The loop never retries its way around it.
                    emit(
                        EventKind.TOOL_RESULT,
                        iterations,
                        tool=call.tool,
                        detail=message,
                        data={
                            "success": False,
                            "error": message,
                            "category": categorize_error(message).value,
                        },
                    )

            if step_nudged:
                continue

        return finish(AgentTerminationReason.MAX_ITERATIONS, final_response)

    def _complete(self, conversation: list[Message], tool_defs: list[ToolDefinition]) -> Response:
        """Call the backend, passing tool definitions when it accepts them."""
        complete: Callable[..., Response] = self._config.backend.complete
        try:
            return complete(conversation, tool_defs)
        except TypeError:
            # Backends in this package take only the conversation; the
            # TypeScript AsyncBackend takes both. Support either rather than
            # forcing every Python backend to grow a parameter it ignores.
            return complete(conversation)

    def _execute_tool(
        self, call: ToolCall, caller: CallerContext
    ) -> tuple[Any, bool, str]:
        """Run one tool call through the policy-enforcing executor.

        Failures are converted into a failed result rather than propagated: a
        raising tool must not take down the run, and the failure has to reach
        the error tracker and the event trace to be auditable.
        """
        if self._config.tool_executor is None:
            return None, False, f"unknown tool {call.tool}: no tool executor configured"

        _, found = self._config.registry.get(call.tool)
        if not found and self._config.registry.names():
            return None, False, f"unknown tool {call.tool}"

        try:
            return self._config.tool_executor.execute(
                call.tool, call.args, caller, self._config.framework
            )
        except PermissionError as exc:
            # AuditedToolClient raises this on a denial. It is already audited;
            # surface it as a denied result so the loop stays observable.
            return None, False, f"denied by policy: {exc}"
        except Exception as exc:
            return None, False, str(exc)

    def _validate(self, resp: Response) -> ValidationResult:
        """Validate a model turn into tool calls, a final answer, or a retry."""
        validator = self._config.validator

        if resp.tool_calls:
            calls = [ToolCall(tool=tc.name, args=tc.arguments) for tc in resp.tool_calls]
            if validator is None:
                return ValidationResult(tool_calls=calls, nudge=None, needs_retry=False)
            return validator.validate_tool_calls(calls)

        if validator is None:
            return ValidationResult(tool_calls=[], nudge=None, needs_retry=False)

        text_validation = validator.validate_text_response(resp.content)
        if text_validation.tool_calls:
            return text_validation
        if self._config.require_tool_call:
            return text_validation
        return ValidationResult(tool_calls=[], nudge=None, needs_retry=False)

    @staticmethod
    def _append_nudge(conversation: list[Message], nudge: Nudge) -> None:
        """Append a nudge to the conversation with its message type."""
        conversation.append(
            Message(
                role=Role.USER,
                content=nudge.content,
                meta=MessageMeta(type=_nudge_meta_type(nudge.kind)),
            )
        )

    @staticmethod
    def _append_tool_message(conversation: list[Message], tool: str, content: str) -> None:
        """Append a tool-result message to the conversation."""
        conversation.append(
            Message(
                role=Role.TOOL,
                content=content,
                meta=MessageMeta(type=MessageType.TOOL_RESULT),
            )
        )
