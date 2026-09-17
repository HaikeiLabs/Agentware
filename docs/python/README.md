# Python Middleware Usage Examples

This document provides examples of how to use the Python middleware
(`pedro_agentware`) for policy enforcement and audit logging. It mirrors the Go
reference implementation in `go/middleware/`.

## Installation

```bash
pip install -e ./python
# or, from the python/ directory:
cd python && pip install -e ".[dev]"
```

The package is not published to PyPI yet. See
[PyPI distribution strategy](pypi-distribution-strategy.md) for the artifact
contract, release process, and the packaging work required before the first
publish.

## Basic Usage

### Creating a Policy

```python
from pedro_agentware.middleware import Action, Condition, Operator, Policy, Rule

policy = Policy(
    default_deny=False,
    rules=[
        Rule(
            name="rate-limit-tools",
            tools=["*"],
            action=Action.ALLOW,
        ),
        Rule(
            name="deny-admin",
            tools=["delete_database", "drop_table"],
            action=Action.DENY,
            conditions=[
                Condition(field="caller.trusted", operator=Operator.EQ, value="false"),
            ],
        ),
    ],
)
```

### Creating Middleware

```python
from pedro_agentware.middleware import CallerContext, MiddlewareImpl

class MyToolExecutor:
    def execute(self, tool_name: str, args: dict) -> tuple:
        # Your tool execution logic here
        return ({"output": f"Executed {tool_name}"}, True, "")

# Create middleware
mw = MiddlewareImpl(MyToolExecutor())

# Call a tool through middleware
result, success, error = mw.execute("read_file", {"path": "/tmp/test.txt"}, CallerContext())
```

### Using Caller Context and Delegation

```python
from pedro_agentware.middleware import CallerContext

# At a human entry point the user IS the invoking subject. Trusted defaults to
# False (fail-closed); it must be set explicitly to be true.
caller = CallerContext(
    trusted=True,
    role="user",
    user_id="user-123",
    session_id="session-456",
    source="cli",
    invoking_subject="user-123",
)

# When the agent spawns a subagent, delegate: the invoking subject is carried
# unchanged and the depth increments, so the audit trail resolves back to the
# human who authorized the request.
subagent = caller.delegate(span="subagent-1")
assert subagent.invoking_subject == "user-123"
assert subagent.delegation_depth == 1
assert subagent.parent_span == "subagent-1"
```

### Audited Tool Client

```python
from pedro_agentware.middleware import AuditedToolClient

async def echo(**kwargs):
    return {"echo": kwargs.get("value", "")}

client = AuditedToolClient(source="my-agent", evaluator=policy_evaluator)

result = await client.Execute(
    tool_name="echo",
    tool_args={"value": "hi"},
    user_id="user-123",
    channel_id="session-456",
    guild_id=None,
    func=echo,
    caller=caller,  # CallerContext; omitted builds a fail-closed untrusted one
)
```

### Using Audit

```python
from pedro_agentware.middleware import AuditFilter, InMemoryAuditor

auditor = InMemoryAuditor()
client = AuditedToolClient(source="my-agent", auditor=auditor)

# After tool calls, query the audit log. Records carry the delegation chain:
# invoking_subject, parent_span, delegation_depth, framework.
records = auditor.query(AuditFilter(invoking_subject="user-123"))
for entry in records:
    print(f"Decision: {entry.decision.action.value}, Tool: {entry.tool_name}")
```

## Condition Operators

| Operator | Description |
|----------|-------------|
| `eq` | Field equals value |
| `not_eq` | Field does not equal value |
| `contains` | Field contains value |
| `not_contains` | Field does not contain value |
| `matches` | Field matches regex pattern |
| `not_matches` | Field does not match regex pattern |
| `exists` | Field exists |
| `not_exists` | Field does not exist |

## Field Resolution

Conditions can reference:

- `caller.role` - Caller's role
- `caller.user_id` - User ID
- `caller.session_id` - Session ID
- `caller.source` - Call source
- `caller.trusted` - Whether caller is trusted
- `args.<name>` - Tool argument values

## Observable Agent Loop

`AgentLoop` runs the model/tool loop — model -> tool call -> tool result ->
model -> answer — with every step observable and every bound explicit. It is the
Python counterpart to `typescript/src/executor/agent_loop.ts`.

```python
from pedro_agentware.executor import AgentLoop, AgentLoopConfig
from pedro_agentware.middleware import LoggingObserver, MiddlewareImpl
from pedro_agentware.middleware.guardrails import ModelCallLimiter, ResponseValidator

loop = AgentLoop(
    AgentLoopConfig(
        backend=backend,
        registry=registry,
        # The policy-enforcing middleware drops in here, so every tool call the
        # loop makes is evaluated and audited.
        tool_executor=MiddlewareImpl(dispatch, evaluator=policy, auditor=auditor),
        validator=ResponseValidator(registry.names()),
        model_call_limiter=ModelCallLimiter(hard_limit=10),
        observers=[LoggingObserver(sink=print)],
        max_iterations=20,
        max_nudges=3,
    )
)

result = loop.run(system_prompt, user_message, session_id="s1", caller=caller)
```

Each run prints a line per step, led by the message count handed to the model:

```text
[agent 1] before_model messages=2
[agent 1] after_model  tool_calls=1 finish=tool_calls tokens=0
[agent 1] tool_call    get_weather {"city": "Denver"}
[agent 1] tool_result  get_weather {"city": "Denver", "temp_c": 14}
[agent 2] before_model messages=4
[agent 2] after_model  tool_calls=0 finish=stop tokens=134
[agent 2] final_answer len=33
[agent -] run_end      reason=complete iterations=2 model_calls=2 tool_calls=1 nudges=0
```

Runnable end to end, with no network or API key:

```bash
python examples/observable_agent_loop.py
```

### Termination

Every bound has its own `AgentTerminationReason`, so "why did this stop" is
answerable from the result alone:

| Reason | Bound |
| --- | --- |
| `complete` | The model produced a final answer. |
| `max_iterations` | `max_iterations` loop passes. |
| `model_call_limit` | `ModelCallLimiter.hard_limit` model calls for the session. |
| `nudges_exhausted` | `max_nudges` corrections; invalid output cannot loop forever. |
| `error` | The model call failed. |

`max_iterations` bounds iterations; `ModelCallLimiter` bounds the thing that
actually costs tokens. A limiter is always created from `max_iterations` when
none is supplied, so the hard cap is never accidentally absent.

### Events

Observers receive `LoopEvent`s in order, each carrying a monotonic `sequence`
and the `message_count` at emit time: `run_start`, `before_model`,
`after_model`, `tool_call`, `tool_result`, `nudge`, `guardrail`, `error`,
`final_answer`, `run_end`. `before_model`/`after_model` always bracket a model
call, including a failed one. `RecordingObserver` collects them for assertions;
`result.events` carries the full trace even with no observer registered.

Observation is a diagnostic, never control flow — observers are wrapped in
`SafeObserver`, so one that raises cannot change a decision or fail a run.

### Authorization

The loop never inspects, substitutes or upgrades a policy decision. Tool calls
go through the injected `tool_executor` with the run's `CallerContext` passed
through unchanged, so fail-closed policy and the audit trail behave exactly as
they do outside the loop. A denial comes back as a failed tool result, is
recorded by the `ErrorTracker`, is surfaced as a `tool_result` event, and is
reported to the model — observable, and still denied. The loop never retries
its way around one.

## Harness Contract

Third-party agent harnesses build against `pedro_agentware` through the
`kei/` module — see `docs/harness-contract.md` and
`python/tests/third_party_harness_test.py` for a complete example that imports
nothing outside this library.

## API Reference

### Core Classes

- `MiddlewareImpl` / `Middleware` - Main middleware class for policy enforcement
- `AuditedToolClient` - Small surface: a tool function in, a result out, audited either way
- `Policy` - Policy container with rules
- `Rule` - Individual policy rule
- `CallerContext` - Context about the caller (with delegation fields and `delegate()`)
- `Decision` - Policy decision result
- `Condition` / `Operator` - Rule conditions and operators

### Agent Loop

- `AgentLoop` / `AgentLoopConfig` - Observable, bounded model/tool loop
- `AgentResult` - Final answer plus `iterations`, `model_calls`, `tool_calls_made`, `nudges`, and the event trace
- `AgentTerminationReason` - Why the loop stopped
- `ModelCallLimiter` - Hard per-session cap on model calls
- `LoopEvent` / `EventKind` - One observable moment and its kind
- `RecordingObserver` / `LoggingObserver` / `FunctionObserver` / `SafeObserver` - Observers

### Auditors

- `InMemoryAuditor` - Stores audit records in memory
- `AuditRecord` - One record per tool call, carrying the delegation chain
- `AuditFilter` - Query filter over `session_id`, `parent_span`, `invoking_subject`, `tool_name`, `action`, `since`, `limit`
