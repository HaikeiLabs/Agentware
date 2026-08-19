# divergence

Places the three implementations disagree, or where a single implementation
diverges from what SPEC.md describes. Ranked by blast radius.

Verified by reading source on branch `feature/kei-proxy-integration`
(forked from `docs/tbox-composable`). Iteration 1 scope: the middleware
execution path only. Adapters, toolformat, and the inference loop's model
handling are not yet audited.

---

## D-001 — `ActionFilter` redacts differently in TypeScript than in Go/Python. Blast radius: HIGH.

Same policy, same input, three different executed calls.

**Go** — `go/middleware/middleware.go:58-62` copies the policy's replacement
values over the caller's args:

```go
if decision.Action == ActionFilter && len(decision.RedactedArgs) > 0 {
    for k, v := range decision.RedactedArgs {
        args[k] = v
    }
}
```

**Python** — `python/src/pedro_agentware/middleware/middleware.py:71-72`, same
semantics, non-mutating:

```python
args = {**args, **decision.redacted_args}
```

**TypeScript** — `typescript/src/middleware/middleware.ts:53-63` ignores the
values entirely, takes only the *keys*, and substitutes the string literal
`"[REDACTED]"`:

```ts
const redactFields = Object.keys(decision.redacted_args)
...
(args as Record<string, unknown>)[field] = "[REDACTED]";
```

Consequences, in order of severity:

1. A policy that filters `{"account_id": "***"}` sends `***` downstream in
   Go/Python and `[REDACTED]` in TypeScript. The executed tool call differs by
   language. This is precisely the failure SPEC.md §2.3 Marshalling names:
   "same input produces the same executed call regardless of adapter."
2. TypeScript's `field in args` guard (line 59) means a redaction naming a key
   **not already present in args** is silently dropped. Go and Python *add* the
   key. A policy that redacts by injecting a field is a no-op in TypeScript.
3. Go mutates the caller's map in place (`args[k] = v` on the passed map).
   Python and TypeScript both copy. A Go caller that reuses its args map after
   a filtered call sees the redaction leak backward into its own data.

Any conformance matrix built before this is fixed will encode the divergence as
expected behavior.

---

## D-002 — Go injects a `Trusted: true` caller when context is absent. Blast radius: HIGH (security).

`go/middleware/middleware.go:77-84`:

```go
func getCallerContext(ctx context.Context) CallerContext {
    if c, ok := ctx.Value(callerContextKey).(CallerContext); ok {
        return c
    }
    return CallerContext{
        Trusted: true,
    }
}
```

A `context.Context` with no caller attached yields an anonymous caller with
empty `UserID`, empty `Role`, empty `SessionID` — and `Trusted: true`. Any
policy rule conditioned on `trusted` fails open. Forgetting to call
`WithCallerContext` is not an error; it is a privilege escalation, and it is
silent.

Python and TypeScript cannot express this bug: both take `caller` as a required
positional parameter (`middleware.py:52-54`, `middleware.ts:30-34`), so an
absent caller is a type error at the call site rather than a trusted default.
The three implementations therefore disagree on whether "no caller" is
permitted at all.

The audit record for such a call has an empty `SessionID`
(`middleware.go:42`), so the fail-open is also invisible in the audit log.

---

## D-003 — `AuditRecord.Timestamp` is never populated. Blast radius: MEDIUM-HIGH.

The field is declared at `go/middleware/audit.go:10` and the record is
constructed at `go/middleware/middleware.go:41-46` **without it** — the struct
literal sets `SessionID`, `ToolName`, `Args`, `Decision`, and stops. Go
zero-values it to `time.Time{}`.

`grep -rn "Timestamp" go/middleware/` confirms `time.Now()` is called only in
`policy.go:59,68,76` (on `Decision`) and in `guardrails/error_tracker.go:51`.
Never on an `AuditRecord`.

Two consequences:

- `InMemoryAuditor.Query` filters on `filter.Since` at `audit.go:52`
  (`r.Timestamp.Before(filter.Since)`). Since every record's timestamp is the
  zero value, **any** `Since` filter after year 1 matches nothing. Time-ranged
  audit queries return empty. Silently.
- SPEC.md §5 builds every metric as a rollup over the audit table. A record with
  no time cannot be bucketed into any time series.

TypeScript does set it (`middleware.ts:44`, `timestamp: new Date()`). Python's
`AuditRecord` construction (`middleware.py:63-70`) omits it, matching Go. So
this is also a 2-of-3 divergence.

---

## D-006 — The hermes adapter has its own private context key. Caller context does not cross the boundary. Blast radius: HIGH.

Two independent `WithCallerContext` functions exist, writing to two different
context keys:

| | Key | Setter | Reader |
|---|---|---|---|
| middleware | `callerContextKey contextKey = "caller_context"` (`go/middleware/middleware.go:86-88`) | `middleware.WithCallerContext` (`middleware.go:90-92`) | `getCallerContext` (`middleware.go:77-84`), `CallerFromContext` (`middleware.go:96-99`) |
| hermes | `hermesCallerKey hermesCallerContextKey = "hermes_caller_context"` (`go/adapters/hermes/adapter.go:277-279`) | `hermes.WithCallerContext` (`adapter.go:279-281`) | `hermes.getCallerContext` (`adapter.go:266-274`) |

The key types differ (`contextKey` vs. `hermesCallerContextKey`) and the string
values differ, so a value written by one is invisible to the other — Go's
`context.Value` matches on both. Concretely:

- A caller set via `hermes.WithCallerContext` is **not** readable by
  `middleware.CallerFromContext`. If a hermes-adapted call reaches the shared
  middleware, `getCallerContext` misses and returns the anonymous
  `Trusted: true` default (D-002).
- Conversely `memory.Executor` reads only `middleware.CallerFromContext`
  (`go/memory/executor.go:47`), so it cannot see a hermes-set caller at all —
  it returns `ErrNoCaller` (`executor.go:49`).

This is D-002's fail-open with a delivery mechanism: the adapter boundary is
exactly where the caller silently becomes anonymous-and-trusted. It is also the
concrete form of SPEC.md §2.3's Policy invariant failing — "same policy yields
the same allow/deny for the same subject, whatever the framework" cannot hold
when the subject does not survive the framework boundary.

Note `hermes.getCallerContext` (`adapter.go:266-274`) is a verbatim copy of
`middleware.getCallerContext` including the `Trusted: true` default — the bug
was duplicated along with the function.

---

## D-007 — `mcp.Server` executes tools with no middleware. Blast radius: HIGH (security).

`go/mcp/server.go:126-127`:

```go
ctx = middleware.WithCallerContext(ctx, s.caller)
res, err := tool.Execute(ctx, p.Arguments)
```

It attaches a caller context and then calls `tool.Execute` **directly on the
registry tool**, not through a `Middleware`. `grep -n "middleware\." go/mcp/server.go`
returns only lines 19, 25, and 126 — the struct field, the constructor
parameter, and the context attach. There is no `NewMiddleware`, no
`PolicyEvaluator`, no `Auditor` anywhere in the file.

So every tool call served over MCP is executed with **zero policy evaluation and
zero audit rows**. The caller context is propagated faithfully and then used
only by the executor for vault scoping (`go/memory/executor.go:47-52`), never
for a policy decision.

This is a third bypass, independent of the two in G-035, and unlike those it is
not hypothetical — it is the shipped behavior of `cmd/memctl`
(`go/cmd/memctl/main.go:73-78`), which constructs the server with
`Trusted: true` hardcoded.

---

## D-008 — Python fails open too, via dataclass defaults rather than a context miss. Blast radius: HIGH (security, in scope).

Correcting an earlier claim in this audit: Python was described as unable to
fail open because `caller` is a required positional parameter
(`python/src/pedro_agentware/middleware/middleware.py:52-54`). That is true of
the *middleware* call and false of the system.

`CallerContext` is a dataclass with every field defaulted
(`python/src/pedro_agentware/middleware/types.py:44-52`):

```python
user_id: str = ""
session_id: str = ""
role: str = ""
source: str = ""
trusted: bool = True          # <-- fail-open default
metadata: dict[str, str] = field(default_factory=dict)
```

So `CallerContext()` constructs an anonymous, **trusted** caller with no
argument at all — the same object Go's `getCallerContext` fabricates on a
context miss (`go/middleware/middleware.go:81-83`), reached more easily.

And it is reached by default. `ExecuteRequest.caller_ctx` is declared
`caller_ctx: CallerContext = field(default_factory=CallerContext)`
(`python/src/pedro_agentware/executor/executor.py:31`), then passed to the tool
executor on every call (`executor.py:97-99`). An `ExecuteRequest` built without
a caller runs the entire agent loop as anonymous-and-trusted, and no type error
occurs — the dataclass default supplies it silently.

TypeScript should be checked for the same pattern before the Python fix is
called complete.

Fix, in scope per the owner's Python-only decision: `trusted` must default to
`False`, and `executor.py:31`'s `default_factory` should be removed so the field
is required. Both are one-line changes; the blast radius is in the tests and any
caller relying on the implicit default.

---

## D-009 — The Pydantic adapter has no middleware integration at all. Blast radius: HIGH (security, in scope).

`grep -rn "middleware\|Middleware\|caller\|Caller\|policy\|auditor" adapters/pydantic/*.py`
returns **nothing**. The adapter (`python/adapters/pydantic/adapter.py`) exposes
`execute(self, tool_name, args)` (line 38) with no caller parameter, and runs the
Pydantic AI agent directly (docstring, lines 39-44: "Pydantic AI agents run as a
full agent loop").

So the adapter that the hackathon demo depends on — the one that is supposed to
be half of SPEC.md §6 core item 4's cross-framework proof — evaluates no policy,
emits no audit row, and has no way to receive a caller identity. It is the
Python equivalent of `mcp.Server` (D-007), on the demo's critical path.

This is the concrete blocker for `parity.md` §2's `AgentBackend` abstraction:
the Pydantic backend has no seam to attach policy or audit to, so that seam is
net-new work rather than a rewiring.

---

## D-010 — Go's hermes adapter reimplements the middleware and drops `ActionFilter`. Blast radius: HIGH (security).

`HermesMiddlewareAdapter.Execute` (`go/adapters/hermes/adapter.go:216-245`) does
not wrap or call `middleware.Middleware`. It **reimplements** the enforcement
sequence inline: `getCallerContext` → `policy.Evaluate` → `auditor.Record` →
deny-check → `executor.Execute`. Structurally the same as
`go/middleware/middleware.go:31-65`, copied rather than delegated.

The copy is incomplete. The middleware handles three actions; the adapter
handles two:

| | middleware.go | hermes adapter |
|---|---|---|
| `ActionDeny` | blocks (`:51-56`) | blocks (`:236-244`) |
| `ActionFilter` | applies `RedactedArgs` (`:58-62`) | **absent** |
| `ActionAllow` | executes (`:64`) | executes (`:246`) |

There is no `ActionFilter` branch anywhere in `adapter.go`. A policy returning
`ActionFilter` falls through the deny-check and reaches
`a.executor.Execute(ctx, toolName, args)` at line 246 with **unredacted args**.
The filter silently becomes an allow.

So the same policy, same subject, same tool yields redacted arguments through
the middleware and raw arguments through the hermes adapter. This is SPEC.md
§2.3's Policy invariant — "same policy yields the same allow/deny for the same
subject, whatever the framework" — failing in the one place two enforcement
paths already coexist. The spec's own note applies: "a gap here is a
vulnerability, not a bug."

Secondary divergences in the same function:

- The adapter attaches `decision.Rule` to the deny result's `Metadata`
  (`:241-243`); the middleware does not (`middleware.go:52-55`). Deny responses
  differ in shape between paths.
- It reads caller context via the private hermes key (`:217`, see D-006), so the
  caller it evaluates policy against is frequently the anonymous
  `Trusted: true` default.
- The audit record is built pre-execution (`:227-234`), inheriting SC-007's
  ordering flaw and SC-009's raw-args capture.

---

## D-011 — Python has no adapter-level enforcement at all. Cross-language divergence in whether policy runs. Blast radius: HIGH (security, demo path).

Go's hermes adapter enforces policy (D-010, imperfectly). **No Python adapter
does.**

`AgentBackend` (`python/adapters/base.py:7-17`) is the Python adapter contract:

```python
def execute(self, tool_name: str, args: dict[str, Any]) -> "AgentResult": ...
def list_tools(self) -> list["AgentTool"]: ...
```

No caller parameter. Every implementer matches it —
`HermesAdapter.execute` (`adapters/hermes/adapter.py:35`),
`KitaruAdapter.execute` (`adapters/kitaru/adapter.py:43`),
`PydanticAdapter.execute` (`adapters/pydantic/adapter.py:39`),
`PydanticAdapterAsync.execute` (`adapters/pydantic/adapter.py:156`).

So the divergence is not per-adapter; it is **in the contract**. No Python
adapter can evaluate policy, because the protocol gives it no identity to
evaluate against.

### The two protocols are structurally incompatible

| | `AgentBackend` (adapters) | `ToolExecutor` (middleware) |
|---|---|---|
| Location | `python/adapters/base.py:10` | `python/src/pedro_agentware/middleware/middleware.py:13-18` |
| Signature | `execute(tool_name, args)` | `execute(tool_name, args)` |
| Returns | `AgentResult` dataclass (`base.py:32-43`) | `tuple[Any, bool, str]` |

Same call shape, **different return types**. An `AgentBackend` therefore does
not satisfy `ToolExecutor`, so no Python adapter can be passed to
`MiddlewareImpl(executor=...)` without an adapter-of-the-adapter.

`grep -rn "AgentBackend|AgentResult" python/src/` returns **nothing** — the
middleware package has never referenced the adapter contract. The two halves of
the Python implementation were designed independently and have no bridge.

**Consequence for the demo**: the Pydantic path — SPEC.md §6 core item 4's
cross-framework proof — cannot be governed today without either changing
`AgentBackend` to carry a caller and return middleware-compatible results, or
writing a bridging executor. This is the concrete content of G-046, and it is
also the first thing `parity.md` §2's `AgentBackend` sketch has to resolve:
**a protocol by that name already exists and is the wrong shape.**

---

## D-004 — `Decision.Rule` is populated but discarded at the audit boundary. Blast radius: MEDIUM.

`Decision` carries a `Rule` field (`go/middleware/types.go:24`) and the policy
evaluator sets it. The middleware embeds the whole `Decision` into the
`AuditRecord` (`middleware.go:45`), so the value does survive into the record —
but the Go default-allow path at `middleware.go:38` constructs
`Decision{Action: ActionAllow, Reason: "no policy configured"}` with **no
`Rule`**, and no `Timestamp`.

TypeScript's equivalent default sets `rule: "default"`
(`middleware.ts:37`). Go and Python leave it empty. So "which rule decided" is
answerable in TypeScript and unanswerable in Go/Python for every
no-policy-configured call — which, per D-005, is also the case where the call is
allowed unconditionally.

Relevant to SPEC.md §4 `policy_id` and §6 core item 3 ("denials logged and
explained").

---

## D-005 — No policy configured means allow-all, in all three. Blast radius: MEDIUM.

`go/middleware/middleware.go:35-39`, `middleware.py:56-59`,
`middleware.ts:35-37`: if no evaluator is attached, the decision is
`ActionAllow` with reason `"no policy configured"`.

Consistent across implementations, so not a parity bug — but worth recording
because it means `NewMiddleware(exec)` with no `.WithPolicy(...)` is a
transparent pass-through that still emits audit rows claiming an `allow`
decision. An audit trail showing "allow" for every call is indistinguishable
from one produced by a policy that actually evaluated and permitted.
