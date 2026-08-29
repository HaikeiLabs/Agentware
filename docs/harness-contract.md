# Harness Contract

This document defines the contract between a third-party harness and the `pedro-agentware` library. A "harness" is a wrapper that connects an LLM agent to tool execution while enforcing security policies.

**Product thesis**: "Bring your own agent." This contract enables any third party to build a harness against this library alone, without reverse-engineering existing implementations.

---

## What a Harness Must Implement

A harness must provide three **required** components:

### 1. AuthProvider

Provides authentication tokens for the KEI API. The library defines the interface:

```python
from pedro_agentware.kei import AuthProvider, OpaqueTokenProvider

# Simple implementation using the built-in opaque token provider
auth_provider = OpaqueTokenProvider(
    token="your-bootstrap-token",  # or use secret_provider
)
```

Or implement the protocol yourself:

```python
from typing import Protocol
from pedro_agentware.kei import TokenInfo, TokenType

class MyAuthProvider(Protocol):
    def get_token(self) -> TokenInfo: ...
    def invalidate(self) -> None: ...
    def get_token_type(self) -> TokenType: ...
```

### 2. ToolExecutor

Executes tools on behalf of agents. The library defines the interface:

```python
from pedro_agentware.kei import ToolExecutor

class MyToolExecutor:
    def execute(self, tool_name: str, args: dict) -> Any:
        # Your tool execution logic here
        if tool_name == "my_tool":
            return {"result": "success"}
        raise ToolNotFoundError(f"Unknown tool: {tool_name}")
```

### 3. SecretProvider

Sources the bootstrap secret (`KEI_HARNESS_TOKEN`). Use the built-in:

```python
from pedro_agentware.kei import EnvSecretProvider

secret_provider = EnvSecretProvider()
```

Or implement your own:

```python
class MySecretProvider(Protocol):
    def get_secret(self, name: str) -> str | None: ...
```

---

## Smallest Working Example

```python
from pedro_agentware.kei import (
    HarnessContract,
    OpaqueTokenProvider,
    EnvSecretProvider,
    ToolExecutor,
    ToolNotFoundError,
)

# 1. Implement ToolExecutor
class MinimalToolExecutor:
    def execute(self, tool_name: str, args: dict) -> dict:
        if tool_name == "echo":
            return {"echo": args.get("message", "")}
        raise ToolNotFoundError(f"Tool not found: {tool_name}")

# 2. Create the contract
contract = HarnessContract(
    auth_provider=OpaqueTokenProvider(token="test-token"),
    tool_executor=MinimalToolExecutor(),
    secret_provider=EnvSecretProvider(),
)

# 3. Validate it
from pedro_agentware.kei import validate_contract
errors = validate_contract(contract)
if errors:
    raise ValueError(f"Contract invalid: {errors}")
```

---

## What Agentware Provides

### Policy Enforcement

The library provides policy evaluation via `PolicyEvaluator`. See `kei/evaluator.py` for the `KeiProxyEvaluator` implementation that connects to the KEI proxy for policy decisions.

```python
from pedro_agentware.middleware import AuditedToolClient

client = AuditedToolClient(
    source="my-harness",
    evaluator=policy_evaluator,  # Your PolicyEvaluator
    auditor=auditor,             # Optional: your Auditor
)
```

### Audit Logging

Every tool call is recorded. Use the built-in or provide your own:

```python
from pedro_agentware.middleware import InMemoryAuditor

auditor = InMemoryAuditor()
# Access records: auditor.query(filter)
```

### CallerContext Delegation

The library tracks human identity across subagent delegation:

```python
from pedro_agentware.middleware import CallerContext

# At human entry point
caller = CallerContext(
    user_id="user-123",
    invoking_subject="user-123",  # The HUMAN
    source="my-harness",
)

# When spawning a subagent
child = caller.delegate(span="agent-1")
# child.invoking_subject remains "user-123"
# child.delegation_depth = 1
```

---

## Fail-Closed Rules

The library enforces fail-closed security. All of these result in **DENY**:

| Condition | Behavior |
|-----------|----------|
| Unknown policy decision | DENY - no implicit allow |
| Unreachable proxy | DENY - cannot bypass policy |
| Missing credential | DENY - no token, no access |
| Expired token | DENY - renewal must succeed |

---

## CallerContext Delegation Rule

**The `invoking_subject` is the HUMAN and is carried UNCHANGED across every delegation hop.**

- `parent_span` and `delegation_depth` record position in the chain
- A subagent running as a service account still resolves to the person who initiated the request
- The `delegate()` method creates child context but preserves `invoking_subject`

This ensures full attribution: every tool call can be traced back to the human who authorized it, even through multiple levels of agent delegation.

---

## Optional Components

These have library defaults:

| Component | Default | Description |
|-----------|---------|-------------|
| `policy_evaluator` | `None` (allow all) | Enforces policy on tool calls |
| `auditor` | `InMemoryAuditor` | Records all tool call decisions |
| `proxy_process` | `None` | Manages local KEI proxy |

---

## File Structure

The contract reuses existing types:

- `kei/config.py` - `HarnessManifest`, `HarnessConfig`
- `kei/auth.py` - `AuthProvider`, `SecretProvider`, `TokenInfo`
- `kei/proxy.py` - `ProxyProcess`, `ProxyConfig`
- `middleware/types.py` - `CallerContext`, `Decision`, `Action`
- `middleware/policy.py` - `PolicyEvaluator`
- `middleware/audit.py` - `Auditor`, `AuditRecord`
- `middleware/tool_client.py` - `AuditedToolClient`
- `kei/evaluator.py` - `KeiProxyEvaluator` (policy-enforcement seam)

---

## Testing

A third-party harness should be testable without importing `pedro-tag` or `pedro_service`. The test in `python/tests/third_party_harness_test.py` demonstrates this by building a complete harness using only `pedro_agentware`.