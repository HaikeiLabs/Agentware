# spec-corrections

---

# PART A — DECISIONS MADE (implementation-ready)

Recorded this session. These close open gaps and are the inputs to the schema
freeze.

## DEC-009 — Token attribution: per model turn

**Tokens are tracked, never enforced.** Confirmed by verification: there is no
budget check, cap, or spend-based denial anywhere in the codebase. The only
behavioral use of token counts is context-window compaction
(`go/middleware/inference/inference.go:77-79`, Python
`middleware/inference.py:130-131`), which decides when to summarize — unrelated
to cost. §4's `tokens_in`/`tokens_out`/`cached_tokens` exist solely to feed §5's
cost rollups.

**Decision: attribute tokens at the turn level.** A model turn emits its own
usage row; tool-call rows do not carry token counts. This matches where the data
actually originates (`llm.Response.UsageTokens`, `go/llm/response.go:8`) and
avoids inventing a split rule across the N tool calls a single turn produces
(`go/executor/inference.go:119`).

Resolves G-049. Consequence: §5's "estimated spend per invocation" is computed by
joining turn rows to task/agent, not by summing per-tool-call values.

## DEC-010 — Decision vocabulary: all four values

The frozen `decision` enum carries **four** outcomes, unioning what the three
repos express today:

| Value | Meaning | Origin |
|---|---|---|
| `allow` | permitted, execute as requested | agentware `ActionAllow` (`go/middleware/types.go:8`) |
| `deny` | blocked | all three repos |
| `filter` | permitted with redacted args | agentware `ActionFilter` (`:10`) |
| `escalate` | not autonomous — route to a human | new; Moderator's governance beat |

Mapping notes for the freeze:
- kei's `permit` → `allow` (rename, SC-005).
- kei's `enrollment_required` is **not** a fourth decision — it is a deny
  subtype / reason code (`kei:cmd/proxy/authorize.go:105,110`). Carry it in
  `reason`, not `decision`.
- pedro-tag's per-tool `permission` (`tool_definitions.py:35`) is a **capability
  name**, not a decision — it is policy *input*, not output. Keep the namespaces
  separate.

Resolves G-044. Unblocks the Moderator's escalation beat (`eval-tasks.md`).

## DEC-011 — Audit transport: local log file, async flush via kei-proxy

Audit rows are written to a **local log file** and **synced/flushed
concurrently** by kei-proxy to the canonical store. Keeps the tool-call path off
the network (addressing the SC-019 latency concern) while leaving kei the owner
of the audit log per DEC-005.

**Durability caveat — state this honestly in the write-up.** Rows exist on local
disk before reaching the canonical store. A container dying between write and
flush loses them. This is a best-effort buffer, not an append-only guarantee.
§13 marks audit never-cut, so the docs should say "local buffer, async flush"
rather than imply durability the design does not provide. Acceptable for the
demo; worth naming.

Supersedes the SC-003 conflict: kei's action_log is no longer a *parallel* sink,
it is the flush target of a single path.

---

# PART B — SPEC CHANGES REQUIRED

Claims in SPEC.md the code contradicts. Each should be edited before submission;
citations are in the SC entries below.

| § | Current claim | Required change | Evidence |
|---|---|---|---|
| §3 | Agent Gateway — **Have** | → **Build** | kei and agentware do not touch; no branch, commit, or code reference (G-028) |
| §3 | Model Armor — **Adapt**, "agentware pre-execution hooks" | → **Build** | tool poisoning + PII are output properties; no post-execution hook exists in any language (SC-006) |
| §3 | Observability — **Have**, "MultiAuditor (OTel/Prometheus/Postgres)" | → **Build** | verified absent: no `MultiAuditor`, no OTel/Prometheus/Postgres anywhere, no metrics package (SC-027) |
| §2.2 | "abstracts across model formats **and** across agent frameworks" | **split into two claims** | model-format is real (`tool_definitions.py:527-546`, Go `toolformat/`); framework abstraction does not exist (SC-014) |
| §4 | `tool_args_digest` | note current behavior is **inverted** | raw args stored, filtered calls log unredacted values (SC-009) |
| §4 | `cached_tokens` | flag as **not captured** | absent from `TokenUsage` and the wire unmarshal, not merely unplumbed (SC-025) |
| §6.4 | "same tool under two frameworks" | qualify: **requires the tool object first** | no framework axis exists yet (D-011) |
| §13 | pedro-tag: "config change and a client swap" | → **rewrite** | pedro-tag imports only `ResponseValidator`; no audit path to swap to (SC-012) |
| §13 | "existing business-analyst agents" | → **rewrite or cut the beat** | tools are GitHub/calendar/web-search; no such agents (SC-013) |
| §13 | cut line, 5 entries | **add a row** for the framework abstraction | now load-bearing and not droppable (SC-015) |
| §12 | fallback: "wrap ADK at the transport layer" | → **treat as dead** | ADK's `before_tool_callback`/`after_tool_callback` make tool-layer cheaper (`parity.md` §5.4) |

**Not a spec edit — missing engineering**: §2.1 delegation is unbuilt in both
repos (SC-016, SC-021). kei's `AuthorizeRequest` carries one identity in two
namespaces (`kei:cmd/proxy/abac.go:13-20`); agentware's `CallerContext` has one
slot (`go/middleware/types.go:13-20`). This is the differentiator and the §8
hero shot.

---

# PART C — ORIGINAL FINDINGS

Places where SPEC.md conflicts with another committed or working-tree artifact.
Distinct from `gaps.md`: a gap is a claim not yet checked against source; a
correction is two documents that cannot both be true. Each needs a human call
on which one is authoritative before the day-3 schema freeze.

Source for all entries below: `docs/kei-proxy-integration-prompt.md`
(untracked, working tree only) read against SPEC.md. No source code was read.

Entries SC-006 onward are verified against source on branch
`feature/kei-proxy-integration`. Each carries a file:line citation.

- [ ] SC-006 status:open risk:high — **"pre- and post-execution" — there is no post-execution hook.**
  SPEC.md §1 framing table instructs saying "Policy enforcement middleware
  intercepts every tool call, **pre- and post-execution**." The code has no
  post-execution interception in any of the three implementations.
  `go/middleware/middleware.go:64` ends the function with
  `return m.exec.Execute(ctx, toolName, args)` — the executor's return value is
  passed straight back to the caller, unread. Identical in
  `python/src/pedro_agentware/middleware/middleware.py:74`
  (`return self._executor.execute(tool_name, args)`) and
  `typescript/src/middleware/middleware.ts:66`
  (`return this.executor.execute(toolName, args)`).
  Searched: `go/middleware/` (all 6 non-test files), the Python and TypeScript
  middleware packages, and `go/executor/inference.go`. No result inspection, no
  post-hook interface, no second `Record` call after execution.
  Consequences: the tool's *result* is never audited, never policy-checked, and
  never scanned. SPEC.md §3 marks Model Armor ("prompt injection, tool
  poisoning, PII") as **Adapt** on the strength of "agentware pre-execution
  hooks" — but tool poisoning and PII are properties of tool *output*, which
  this path cannot see. That row is **Build**, not Adapt.

- [ ] SC-007 status:open risk:high — **`resources_touched[]` and the result are structurally unreachable.**
  SPEC.md §4 requires `resources_touched[]` ("resource identifiers, not tool
  names") per audit record, and §13 marks it never-cut. The audit record is
  constructed at `go/middleware/middleware.go:41-46` — **before**
  `m.exec.Execute` is called at line 64 — and `m.auditor.Record(auditRecord)`
  fires at line 48, also before execution. The record is written and closed
  while the tool has not yet run. Nothing after execution can amend it: the
  `Auditor` interface (`go/middleware/audit.go:13-16`) exposes only `Record`
  and `Query`, with no update or amend method.
  Therefore every §4 field whose value is only knowable *after* the call —
  `resources_touched[]`, `latency_ms`, `error`, `retry_count`, `tokens_in`,
  `tokens_out`, `cached_tokens` — cannot be populated without restructuring the
  emission point. This is not a field-addition task. See G-033.

- [ ] SC-008 status:open risk:high — **The audit record has 4 of the spec's 15 fields.**
  SPEC.md §4 specifies: `invoking_subject`, `agent_id`, `agent_version`,
  `parent_span`, `delegation_depth`, `framework`, `tool_name`,
  `tool_args_digest`, `resources_touched[]`, `decision`, `policy_id`, `model`,
  `tokens_in`, `tokens_out`, `cached_tokens`, `latency_ms`, `error`,
  `retry_count`.
  `AuditRecord` (`go/middleware/audit.go:5-11`) has exactly five fields:
  `SessionID`, `ToolName`, `Args`, `Decision`, `Timestamp` — and `Timestamp` is
  never set (see divergence.md D-003), so four are populated. Mapping:
  `ToolName` → `tool_name`; `Decision.Action` → `decision`; `Decision.Rule` →
  `policy_id` (partially — empty on the default-allow path, D-004).
  `SessionID` is **not** `invoking_subject`: it is a session identifier copied
  from `CallerContext.SessionID` at `middleware.go:42`, and `CallerContext`
  (`go/middleware/types.go:13-20`) has no subject-chain field at all.
  Absent entirely: `invoking_subject`, `agent_id`, `agent_version`,
  `parent_span`, `delegation_depth`, `framework`, `resources_touched[]`,
  `model`, `tokens_in`, `tokens_out`, `cached_tokens`, `latency_ms`, `error`,
  `retry_count`. `tool_args_digest` is absent and inverted — see SC-009.
  SPEC.md §13 describes agentware's change as "emit the audit record at the
  interception point," which reads as wiring an existing record to a sink. The
  record does not exist. This is the schema, not the plumbing.

- [ ] SC-009 status:open risk:high — **Raw args are stored, not a digest. Inverted from spec.**
  SPEC.md §4: "`tool_args_digest` — Digest not raw args — avoids logging PII
  into the audit store." `AuditRecord.Args` is `map[string]any`
  (`go/middleware/audit.go:8`) and receives the caller's args by reference at
  `go/middleware/middleware.go:44`. No hashing, no digesting anywhere in the
  package.
  Worse, the ordering defeats the redaction that does exist: the record is built
  at lines 41-46 with the **pre-filter** args, and `ActionFilter` applies its
  redactions afterward at lines 58-62. So on a filtered call the audit store
  receives the *unredacted* values and the tool receives the redacted ones —
  exactly backwards from the intent. In Go the aliasing then makes it
  nondeterministic: line 60 mutates the same map the audit record holds a
  reference to, so `InMemoryAuditor`'s stored record retroactively shows
  redacted values, while a sink that serialized on receipt would have captured
  the raw ones. Python (`middleware.py:72`) and TypeScript
  (`middleware.ts:57`) rebind rather than mutate, so their audit records keep
  the raw args permanently.
  A PII-redaction policy today writes PII into the audit store. Tracked as
  G-034.

- [ ] SC-010 status:open risk:medium — **Nothing structurally requires the middleware to be in the path.**
  SPEC.md §2.3: "Same policy yields the same allow/deny for the same subject,
  whatever the framework. A gap here is a vulnerability, not a bug."
  `InferenceExecutorConfig.ToolExec` (`go/executor/executor.go:76`) is typed
  `middleware.ToolExecutor` — the bare two-method interface from
  `middleware.go:9-11`, not `middleware.Middleware` (`middleware.go:13-17`).
  `tools.RegistryExecutor` (`go/tools/executor.go:6-8`) satisfies
  `ToolExecutor` directly. So
  `NewInferenceExecutor(InferenceExecutorConfig{ToolExec: tools.NewRegistryExecutor(reg)})`
  compiles, runs, executes every tool, and consults no policy and writes no
  audit row. The comment at `executor.go:75` ("typically a Middleware wrapping
  a registry dispatch") is the only thing asking for it — "typically" is
  carrying the entire security model.
  The inference loop calls it unconditionally at
  `go/executor/inference.go:121` with no interface assertion. Combined with
  D-002 (absent caller ⇒ `Trusted: true`), there are two independent silent
  fail-open paths. This is the concrete form of the SC-001 question.

Entries SC-011 onward come from the owner's code review of **pedro-tag**
(reported this session, not independently verified from this repo — pedro-tag
is a separate codebase). They settle SC-002.

- [ ] SC-011 status:open risk:high — **pedro-tag uses Pydantic AI, not ADK.**
  SPEC.md §6 core item 4 requires "same tool executing under two frameworks (ADK
  + native harness)" and §7 makes ADK mandatory. Owner's review of pedro-tag
  found zero ADK imports; it uses Pydantic AI exclusively. `tool_definitions.py`
  contains **model API** renderers (OpenAI/Anthropic/Ollama) — the model-format
  axis — not agent-framework adapters. So pedro-tag is not currently a
  cross-framework proof point of anything; it is a single-framework consumer.

- [ ] SC-012 status:open risk:high — **"config change + client swap" is refuted.**
  SPEC.md §13: "The scope is a config change and a client swap." Owner's review
  found pedro-tag imports only `ResponseValidator` (guardrails) from
  pedro_agentware — no tool-call interception layer, no audit integration. There
  is no client to swap: the audit path pedro-tag would swap *to* does not exist
  on either side. Combined with SC-006/SC-007/SC-008 (agentware's emitter is
  pre-execution only and the record has 4 of 18 fields), the spec's cheapest
  line item is one of its most expensive.

- [ ] SC-013 status:open risk:medium — **"existing business-analyst agents" do not exist.**
  SPEC.md §13: "existing business-analyst agents, written before any of this,
  getting audited with no rewrite. That is a genuinely strong claim and it's 25
  seconds of demo." Owner's review found pedro-tag's tools are GitHub, calendar,
  and web-search — developer ops. No business-analyst agents. The demo beat as
  written describes agents that were never built; either the beat changes to
  what exists, or it is cut. Low engineering cost, but it is a claim currently
  scheduled into the §8 demo at 3:15–3:40.

- [ ] SC-014 status:open risk:medium — **§2.2's two claims need splitting in the write-up.**
  "Agentware already abstracts tool definitions across model formats and across
  agent frameworks" is one sentence carrying two claims with very different
  support. Model-format abstraction is real (`toolformat/` in Go,
  `tool_definitions.py` in Python). Agent-framework abstraction does not exist
  in any language (SC-011, and no adapter in this repo). Presented as one claim
  to a judge, the true half makes the false half sound verified. Split it, or
  claim only the half that ships. See `parity.md` §1.

- [ ] SC-015 status:open risk:medium — **§13's cut line is missing a row.**
  The cut line drops pedro-tag integration at #3, reasoning "the claim survives;
  the risk doesn't." That reasoning holds only while pedro-tag is a thin
  consumer. Per DEC-002 (`parity.md` §4) the framework abstraction now lives in
  pedro-agentware — correctly — but it is load-bearing for §6 core item 4 and is
  **not** droppable, and no cut-line entry represents it. Dropping pedro-tag no
  longer sheds the cross-framework risk; it only sheds the demo beat.

- [ ] SC-016 status:partially-resolved risk:high — **There is no delegation model. `CallerContext` cannot carry an invoking subject through a hop.**
  **DEC-003 (owner, this session): delegation is owned by kei-proxy, which
  agentware interacts with via CLI and an adapter.** agentware does not build a
  chain; it receives a subject and records it. This closes the ownership
  question and substantially shrinks the work.
  **Still open**: agentware must still *carry* what kei hands over, and today it
  cannot. `CallerContext` (`go/middleware/types.go:13-20`) has one identity slot
  (`UserID`). A resolved chain (human → parent agent → subagent) flattened into
  `UserID` can represent the immediate caller **or** the invoking human, not
  both — losing exactly the distinction §4's `invoking_subject` and §2.1 require.
  Remaining scope: add subject/parent-span/depth fields to `CallerContext`,
  populate from the adapter, carry into `AuditRecord`. Bounded — days, not a
  subsystem. Tracked as G-040.
  **Critical dependency**: this only works if the adapter's caller context
  actually reaches the middleware. It currently does not — see SC-018/D-006,
  now on the critical path rather than a parity nit.
  Original finding retained below.
  SPEC.md §2.1 is the thesis: "When a parent agent spawns a subagent, the
  kei-minted scope carries the invoking human subject with it. Every downstream
  tool call and every data access resolves back to a person, not a service
  account." §4 requires `invoking_subject` ("survives every delegation hop"),
  `parent_span`, and `delegation_depth`.
  `CallerContext` (`go/middleware/types.go:13-20`) has six fields: `UserID`,
  `SessionID`, `Role`, `Source`, `Trusted`, `Metadata map[string]string`. There
  is **one** identity slot (`UserID`) and no chain, no parent pointer, no depth
  counter, no span id.
  Searched for a delegation concept: `grep -rn "CallerContext{" go/ --include=*.go`
  returns exactly three non-test construction sites — `middleware.go:81` (the
  anonymous fail-open default), `cmd/memctl/main.go:73`, and
  `adapters/hermes/adapter.go:270`. None derives a caller from a parent caller.
  No spawn, delegate, or child-context helper exists anywhere in `go/`.
  Consequently `invoking_subject`, `parent_span`, and `delegation_depth` are not
  "fields to add to the audit record" — there is no data structure in which they
  could be populated. The A-spawns-B case has no representation: B's
  `CallerContext` is constructed fresh or inherited whole, and either way the
  distinction between "the human who started this" and "the agent making this
  call" cannot be expressed.
  **Rule 5 — flagged for human decision. See G-003/G-004 and the questions in
  the session summary.**

- [ ] SC-017 status:open risk:high — **`mcp.Server` bypasses the middleware entirely — a shipped, not hypothetical, bypass.**
  SPEC.md §1: "Policy enforcement middleware intercepts **every** tool call."
  `go/mcp/server.go:126-127` attaches a caller context and calls
  `tool.Execute(ctx, p.Arguments)` directly on the registry tool. The only
  `middleware.` references in the file are lines 19, 25, and 126 — field,
  constructor param, context attach. No `NewMiddleware`, no evaluator, no
  auditor.
  `cmd/memctl` (`go/cmd/memctl/main.go:71-78`) is a shipped binary built on this
  path, constructing the server with `Trusted: true` hardcoded. Every memory
  tool call it serves — `writePage`, `ingest`, `query`, `getClaims`, `lint`
  (`go/memory/executor.go:53-64`) — executes unpoliced and unaudited.
  This is a third bypass independent of the two in G-035. See `divergence.md`
  D-007.

- [ ] SC-018 status:open risk:high — **The hermes adapter's caller context is invisible to the middleware.**
  Two `WithCallerContext` functions write to two different context keys with
  different key *types*: `middleware.callerContextKey` ("caller_context",
  `go/middleware/middleware.go:86-88`) and `hermes.hermesCallerKey`
  ("hermes_caller_context", `go/adapters/hermes/adapter.go:277-279`). Go matches
  `context.Value` on type and value, so neither can read the other's.
  A caller set by the hermes adapter therefore arrives at the shared middleware
  as a miss, and `getCallerContext` (`middleware.go:77-84`) substitutes the
  anonymous `Trusted: true` default. SPEC.md §2.3's Policy invariant — "same
  policy yields the same allow/deny for the same subject, whatever the
  framework" — fails at the only adapter boundary that currently exists, before
  ADK is added. See `divergence.md` D-006.

Entries SC-019+ verified against the **kei** repo at
`/Users/soypete/code/kei/cmd/proxy` (read this session). Citations are
kei-repo-relative.

- [x] SC-019 status:accepted-risk risk:medium — **kei-proxy authorize is a network call today; local-config lookup is the intended design.**
  Today's code path is HTTP: `authorizeTool` (`cmd/proxy/authorize.go:44-53`)
  calls `p.abac.Authorize(...)`, which POSTs to
  `{ABAC_URL}/api/v1/authorize` (`cmd/proxy/abac.go:52-58`) with a 30s default
  timeout (`authorize.go:126`). On permit it may make two more network calls —
  OIDC bridge (`authorize.go:73`) and credential-admin (`authorize.go:94`).
  CLI invocation adds a process spawn and a fresh SQLite open per call
  (`cmd/proxy/store.go:33-51`).
  **DEC-004 (owner, this session): accepted for the demo and hackathon.** The
  preferred design — a local-config permission lookup guarded by Go mutexes,
  with config updates applied by an async concurrent process — is to be
  documented in the **kei** repo for future iterations, not built in the 13 days.
  `ABACClient` is an interface (`cmd/proxy/abac.go:29-31`), so the swap is
  clean when it happens; `NewABACClient` (`abac.go:36`) returns the HTTP
  implementation and `runAuthorize` wires it at `authorize.go:186`.
  **Residual issue to carry**: while authorization is a network call in the demo
  path, §4's `latency_ms` measures authorization + execution unless the two are
  timed separately. Cheap to handle at the emission point; noted so the cost
  metric is not silently wrong. See G-042.

- [x] SC-020 status:resolved — **Audit ownership: kei.**
  **DEC-005 (owner, this session): the audit log is handled in the kei repo.
  agentware does not need to know — it is a proxy action.**
  This settles the SC-003 conflict and the "which sink is canonical" question:
  kei's `action_log` (`cmd/proxy/store.go:23-32`) is the audit path, written by
  the proxy at `authorize.go:113-121`. agentware's `Auditor` is not the platform
  audit record.
  **Consequences, which should be reflected in the schema freeze:**
  - SC-007 (agentware's pre-execution emission point) and SC-008 (4-of-18
    fields) drop out of the hackathon critical path. They remain real defects of
    agentware's own auditor but no longer block §4.
  - The §4 field set must be satisfied by kei's table, which today has six
    columns and is missing 15 of them — including every post-execution value
    (`latency_ms`, `error`, `retry_count`, token fields), which it cannot
    populate because it is written *before* the tool runs (`authorize.go:113`).
    That ordering problem moves to kei; it does not disappear.
  - Token/usage capture (§4 `model`, `tokens_*`) originates at the model
    response, which the proxy never sees. A path from agentware's model layer to
    kei's log still has to exist, or §5's cost metrics have no source. Tracked
    as G-043.

- [ ] SC-021 status:blocked-on-human risk:high — **No delegation chain crosses the kei boundary. `AuthorizeRequest` carries one identity.**
  Per DEC-003 kei-proxy owns delegation. The wire contract does not express it.
  `AuthorizeRequest` (`cmd/proxy/abac.go:13-20`) carries `HarnessToken`,
  `UserID`, `ProviderUserID`, `Action`, `Resource`, `Service`. `UserID` and
  `ProviderUserID` are the *same person* in two namespaces — `configFromEnv`
  defaults `ProviderUserID` to `*user` when unset (`authorize.go:151-153`) —
  not a human→agent chain. There is no parent scope, span, or depth field.
  `AuthorizeResponse` (`abac.go:22-27`) returns `Decision`, `Reason`, `OrgID`,
  `UserID` — no chain either. `AuthorizeOutput` (`authorize.go:22-27`), the CLI's
  JSON, returns `Decision`, `Reason`, `Service`, `Credential`.
  So as built, kei-proxy authorizes **a user for a tool**, one hop, no
  delegation. SPEC.md §2.1's "kei-minted scope carries the invoking human
  subject" through a spawn is not implemented on either side of the boundary.
  This is the thesis and it is currently unbuilt in both repos. **Rule 5.**

- [ ] SC-022 status:open risk:medium — **Terminology conflict: `decision` has three values in kei, three different ones in agentware.**
  kei-proxy emits `permit` / `deny` / `enrollment_required`
  (`authorize.go:63,105,110,116`; the CLI `log` flag documents all three,
  `cmd/proxy/log.go:13`). agentware's `Action` constants are `allow` / `deny` /
  `filter` (`go/middleware/types.go:7-11`).
  Only `deny` is shared. `permit`≠`allow` is cosmetic (SC-005), but the real
  problems are structural: agentware has no `enrollment_required` state, and kei
  has no `filter`/redaction concept. A tool call that agentware would *filter*
  has no kei representation, and an `enrollment_required` result has no
  agentware `Action`. **Rule 3 — two repos disagree on a term. Needs a decision
  before the schema freeze.**

**DEC-006 (owner, this session)**: fail-open fixes are scoped to the
**caller-context default only**, **Python only**, for the hackathon. The
nil-evaluator allow-by-default (`middleware.py:56-59` and counterparts) and the
Go/TypeScript equivalents are deferred to a GitHub issue covering all three
languages.

- [ ] SC-023 status:open risk:medium — **kei-proxy fails closed; agentware fails open. Opposite defaults.**
  kei-proxy: an ABAC error returns an explicit error wrapped
  `"authorization unavailable (fail closed)"` (`authorize.go:53-55`), and
  `runAuthorize` exits non-zero on deny (`authorize.go:229-231`).
  agentware: a missing caller context yields `CallerContext{Trusted: true}`
  (`go/middleware/middleware.go:81-83`), and a missing evaluator yields
  `ActionAllow` (`middleware.go:38`).
  Composing a fail-closed authorizer with a fail-open middleware gives the
  weaker guarantee wherever agentware is in front. Worth settling as a stated
  invariant, not an accident of two teams' defaults.

- [ ] SC-024 status:open risk:high — **Token capture exists but is discarded. It reaches context management, never audit or cost.**
  SPEC.md §13 assigns agentware "token capture from model responses"; §5 requires
  "compute from usage metadata on each model response; never estimate from
  character counts"; §4 lists `tokens_in`, `tokens_out`, `cached_tokens`.
  **The capture half is real** — correcting G-007's assumption that only
  character-count estimation exists. `llm.Response.UsageTokens`
  (`go/llm/response.go:8`) is a `TokenUsage{PromptTokens, CompletionTokens,
  TotalTokens}` (`response.go:19-23`), populated from the backend's reported
  `usage` object — `go/llm/server.go:106-109` unmarshals `prompt_tokens` /
  `completion_tokens` / `total_tokens` and assigns them at `server.go:134-138`.
  Python mirrors it (`python/src/pedro_agentware/llm/response.py:14-35`).
  **The delivery half does not exist.** Searching every non-test consumer of
  `UsageTokens`/`TokenUsage` outside `go/llm/` returns exactly one:
  `go/middleware/inference/inference.go:77-79`
  ```go
  if cfg.ContextManager != nil && resp.UsageTokens.TotalTokens > 0 {
      cfg.ContextManager.UpdateTokenCount(resp.UsageTokens.TotalTokens)
  }
  ```
  That is context-window accounting — deciding when to compact. It reads only
  `TotalTokens`, discards the prompt/completion split, and writes to a context
  manager, not an auditor. Python is identical
  (`python/src/pedro_agentware/middleware/inference.py:130-131`).
  The only other reader is the proxy, which re-serializes usage into its own
  HTTP response (`go/llm/proxy/handler.go:227-231`) — passthrough to the client,
  not capture for audit.
  So: usage metadata enters the process, is used for one purpose, and is dropped.
  No path exists from `llm.Response` to any audit record, in either language.

- [ ] SC-025 status:open risk:high — **`cached_tokens` is not captured at all.**
  §4 lists `cached_tokens` as a field and §5 warns "context caching changes
  effective rates" — making it load-bearing for honest cost numbers.
  `grep -rn "cached\|Cached" go/llm/ go/middleware/` returns **nothing**.
  `TokenUsage` has three fields (`go/llm/response.go:19-23`); the JSON
  unmarshal target at `go/llm/server.go:106-109` declares three keys. Neither
  includes a cached-token field, so the value is not read off the wire even
  when a backend reports it.
  Adding it is small — one struct field and one JSON tag per language — but it
  is currently absent, not merely unplumbed.

- [ ] SC-026 status:open risk:high — **The audit record and the token data are on opposite sides of the tool/model boundary, in different packages.**
  A structural note the §4 schema does not acknowledge. Token usage is a
  property of a **model response** (`llm.Response`, one per inference turn).
  The audit record is a property of a **tool call** (`middleware.AuditRecord`,
  one per tool invocation, `go/middleware/audit.go:5-11`). One inference turn
  can produce several tool calls (`go/executor/inference.go:119`, a loop over
  `toolCalls`), and one task produces many turns.
  So §4's per-tool-call record cannot carry per-turn token counts without a
  defined attribution rule: split across the turn's tool calls, attribute to the
  first, or emit turn-level rows separately. §5's "estimated spend per
  invocation" and delegation rollup depend on which is chosen.
  This is a **schema-freeze decision**, not an implementation detail, and it
  applies wherever the record ends up living — including kei's `action_log`
  under DEC-005, which has no turn concept at all
  (`kei:cmd/proxy/store.go:23-32`).

- [ ] SC-027 status:open risk:high — **`MultiAuditor` does not exist. Neither do any of its three named sinks. Neither does a metrics layer.**
  SPEC.md §3 marks Observability — "OTel audit logs, reasoning traces" — as
  **Have**, implemented by "agentware MultiAuditor (OTel/Prometheus/Postgres)".
  Searched and found nothing:
  - `grep -rn "MultiAuditor\|multi_auditor\|MultiAudit"` across `go/`,
    `python/`, `typescript/` — **zero results.**
  - `grep -rln "otel\|opentelemetry\|prometheus\|postgres\|pgx\|lib/pq"` across
    `go/`, `python/src/`, `python/adapters/`, `typescript/src/` — **zero files.**
  - `go/go.mod` contains no OTel, Prometheus, or Postgres dependency.
  - No metrics/telemetry/observability package exists in any language (listed
    `go/`, `python/src/pedro_agentware/`, `typescript/src/`).
  **The only `Auditor` implementation in any language is `InMemoryAuditor`**:
  Go `go/middleware/audit.go:26-38` (an in-process `[]AuditRecord` slice),
  Python `python/src/pedro_agentware/middleware/audit.py:51-57`, TypeScript
  `typescript/src/middleware/audit.ts:25-28`. It has no persistence, no export,
  and no network sink — records live in a slice until the process exits.
  So §3's Observability row is **Build**, not Have, and the gap is the whole
  capability rather than an integration. Note this does not conflict with
  DEC-005/DEC-011 (kei owns the audit log) — but it does mean agentware has no
  existing sink to write the local log file from, so DEC-011's writer is
  net-new code too.

- [ ] SC-028 status:open risk:high — **The `agentware_` metric families do not exist.**
  SPEC.md §5: "All metrics are rollups over the audit table… Extends the
  existing `agentware_` metric families."
  `grep -rn "agentware_"` across `go/`, `python/src/`, `typescript/src/`
  returns **zero results**. There are no metric families to extend.
  Counter/Gauge/Histogram-style symbols appear only as internal bookkeeping —
  rate-limit counters (`go/middleware/ratelimit.go`), context-window token
  counts (`go/llm/context_window.go`), job counters (`go/jobs/manager.go`) —
  none exported as metrics.
  The §5 framing ("extends the existing families") implies incremental work over
  a working metrics pipeline. Every metric in §5 — utilization, governance,
  reliability, cost — is net-new, and so is the pipeline itself.
  Resolves G-020's open question in the opposite direction from the concern
  filed: there is no *parallel* instrumentation path violating §5's rule,
  because there is no instrumentation path at all.

- [ ] SC-001 status:blocked-on-human — **Enforcement point: shared middleware vs. per-agent call.**
  SPEC.md §1 framing table: "Policy enforcement middleware intercepts every tool
  call, pre- and post-execution", and §6 core item 3 places enforcement "at the
  gateway". The integration prompt instead puts the authorization call in each
  agent's own code (`agent.py`, "before each tool execution"), above agentware's
  middleware entirely. These are different architectures with different security
  properties: middleware interception is unbypassable by construction, per-agent
  calls are unbypassable only if every agent author remembers. §2.3 says a policy
  gap "is a vulnerability, not a bug". Needs a decision on which is the real
  design.

- [x] SC-002 status:resolved — **Repo ownership of the integration.**
  Resolved this session by the owner's pedro-tag review (SC-011, SC-012) and
  DEC-002 in `parity.md` §4: pedro-tag's role was **understated**, not misfiled.
  "Config change + client swap" does not describe the work. The framework
  abstraction lives in pedro-agentware; pedro-tag remains a consumer. Original
  entry retained below for context.

- [ ] SC-002-orig status:superseded — **Repo ownership of the integration.**
  The file lives in `pedro-agentware/docs/` and is named for it, but line 3
  reads "Use this prompt in an opencode session on pedro-tag", and every path it
  names (`src/pedro_service/*`) is pedro-tag's. SPEC.md §13 assigns pedro-agentware
  to Claude and pedro-tag to opencode, and scopes pedro-tag to "a config change
  and a client swap — consumer, not contributor". Implementing an authorization
  client inside pedro-tag exceeds that scope and is the exact scope-creep §13
  flags. Either the file is misfiled, or pedro-tag's role in the spec is
  understated.

- [ ] SC-003 status:blocked-on-human — **Second audit sink.**
  SPEC.md §4 specifies "one append-only record per tool call … the single source
  of truth", and §5: "no parallel instrumentation path — if a number can't be
  derived from an audit row, it doesn't ship." The integration prompt has
  kei-proxy maintaining its own action log in local SQLite
  (`/data/kei-proxy/kei-proxy.db`), with "all actions are logged to kei-proxy
  action log" as a success criterion. That is a second sink, per-container and
  not the Cloud SQL audit store. Either it feeds the canonical record or it
  violates the stated rule.

- [ ] SC-004 status:blocked-on-human — **"Have" overstates the gateway.**
  SPEC.md §3 marks Agent Gateway ("kei proxy + agentware middleware") as **Have**,
  and §3's closing note leans on it: "four of seven capabilities predate the
  hackathon, which is why the remaining time goes into the demo rather than into
  scaffolding." The integration between the two components is unwritten — no
  branch, no commit, no code reference to kei anywhere in this repo; the only
  artifact is this unimplemented prompt. The two halves exist; the gateway does
  not. If **Have** should be **Build**, the §11 timeline and the §13 "risk:
  Medium" rating for kei-proxy both need revisiting. Tracked as G-028.

- [ ] SC-005 status:open risk:medium — **Decision vocabulary mismatch.**
  SPEC.md §4 specifies the audit `decision` field as "allow / deny". The
  integration prompt's `AuthorizationResult.decision` is `"permit"` or `"deny"`.
  Trivial to reconcile, but it is exactly the kind of cross-repo drift the day-3
  schema freeze exists to prevent — fix it in the frozen schema, not in six
  adapters later.
