# parity

What deterministic parity means in this repo, concretely — and the design note
for the framework abstraction that makes it achievable.

Status: design note, not implemented. Written on branch
`feature/kei-proxy-integration`. No source modified.

---

## 1. Two axes, not one

SPEC.md §2.2 says agentware "abstracts tool definitions across model formats
**and** across agent frameworks." These are separate axes and the repo's
coverage of them is very different.

| Axis | What varies | Status in repo |
|------|-------------|----------------|
| **Model format** | How a tool call is *spelled* — llama vs. mistral vs. qwen vs. nemotron vs. minimax syntax | **Exists and works.** Go `toolformat/` (per-family formatter + selector); Python `tool_definitions.py` renders OpenAI/Anthropic/Ollama. |
| **Agent framework** | Who owns the loop, when tools get invoked, where a policy check can be inserted | **Absent.** No framework adapter in any language. pedro-tag uses Pydantic AI directly, zero ADK imports (owner's code review, this session). |

This distinction matters for scoping and it matters for the write-up. The
model-format work is genuine and reusable — it sits *underneath* the framework
abstraction, unchanged. Templating a tool call into model-specific syntax does
not address which framework drives the loop, so it cannot deliver §2.2's second
claim on its own.

Keep these separate in the conformance matrix (§2.3 deliverable): a tool ×
model-format cell and a tool × framework cell are different tests with
different current pass rates.

---

## 2. The proposed abstraction

Owner's framing, this session: pedro-agentware grows a Python interface that
both a Pydantic AI backend and an ADK backend implement, exposing one object
subagents call to make tool calls. Policy and audit attach to the shared
interface, so both paths emit the same record shape.

This is the correct location for it. The alternative — building it in pedro-tag
— would put the abstraction inside a component SPEC.md §13 lists at cut-line
position 3 ("drop pedro-tag integration"). See DEC-002 below.

Sketch, illustrative only — not a committed API:

```
AgentBackend (Protocol)
  ├─ render_tools(tools) -> framework-native tool defs   # delegates to
  │                                                       # existing model-format layer
  ├─ run(prompt, tools, caller) -> Result                 # owns the loop
  └─ framework_name -> str                                # stamps AuditRecord.framework (§4)

  implemented by: PydanticAIBackend, ADKBackend
```

The tool-call path from every backend routes through the existing middleware, so
policy evaluation and audit emission happen once, in one place, regardless of
framework. That is what makes §2.3's Policy invariant ("same policy, same
allow/deny, whatever the framework") testable rather than aspirational.

**Resolved in §5**: ADK replaces the orchestration layer rather than composing
with Pydantic AI — so ADK is a second *backend*, not a layer beneath the first.
The abstraction was deliberately agnostic to this, and holds either way.

---

## 2a. Tool templates — ownership and the new tool object

**DEC-008 (owner, this session).**

- Tool **templates** live in **pedro-tag**. They are generic and
  framework-agnostic — schema and intent, not implementation.
- pedro-agentware gains a **new tool object** that consumes a template and
  implements it against a framework's tool-call form: Pydantic AI and ADK.
  Integration lives in agentware; both backends go through it.
- pedro-tag's **existing Pydantic agents are not migrated.** They stay as
  written. This is a scope boundary on legacy agents, not a deferral of the
  Pydantic backend — the backend is in scope, the rewrite of old agents is not.

This resolves G-025: pedro-agentware defines no concrete tools of its own. It
holds a registry and executor for caller-supplied tools, and now a renderer for
pedro-tag's templates. The §2.3 conformance matrix therefore has rows only once
templates are pulled in — there is nothing local to enumerate.

### Layering — two axes, not one pipeline stage

The new tool object renders per **framework**. The existing `toolformat/` (Go)
and `tool_definitions.py` (Python) render per **model format**. A tool going out
through ADK to Gemini passes through both. The interface should state which
layer owns what, or the two will grow overlapping responsibilities — this is
`parity.md` §1's two axes made concrete in one code path.

### Open interface questions

Neither is answerable from this repo; both shape the interface and should be
settled before it is written.

1. **What is in a template?** If pedro-tag's templates are JSON Schema + name +
   description, the tool object is a renderer. If they carry execution logic or
   handler references, it is also a loader — a materially different interface.
   Needs pedro-tag read.

2. **Does the tool object execute, or only render?**
   - *Render-only*: the framework invokes the tool, and the policy check lives in
     the framework's hook — ADK's `before_tool_callback` (§5.2) makes this
     viable, but each framework needs its own hook wiring.
   - *Execute-through*: agentware owns the call and policy is inline and
     uniform, but ADK's loop must be persuaded to delegate.
   This choice determines where the audit row is emitted, so it interacts with
   DEC-005 (kei owns the audit log).

### Non-negotiable in the interface

The signature **must carry a caller**. Both current Python adapters are
`execute(tool_name, args)` with no caller parameter
(`adapters/pydantic/adapter.py:38`, `adapters/kitaru/adapter.py:42`), which is
why neither can evaluate policy (G-046). Repeating that signature in the new
tool object rebuilds the same hole one layer up, in the component the whole
cross-framework claim rests on. Cheap to get right now; expensive later.

---

## 3. Sequencing

Confirmed with owner this session: **SC-007 lands first.**

1. **SC-007 — restructure the audit emission point.**
   Today the record is built and `Record()`d at
   `go/middleware/middleware.go:41-48`, *before* the executor runs at line 64,
   and `Auditor` (`go/middleware/audit.go:13-16`) exposes only `Record`/`Query`
   — no amend. Any post-execution field is unreachable.
2. **SC-008 — grow the record** from 4 populated fields to §4's 18.
   Needs (1) done, since 7 of the missing fields are post-execution values.
3. **Framework abstraction** — built against the corrected emitter.
4. **ADK backend** — full tool-layer, or §12's transport-layer fallback.

Rationale for this order: an abstraction built against the current
write-before-execute emitter gives *both* backends a record that cannot carry
`resources_touched[]`, `latency_ms`, or any token field. Fixing it afterward
means rebuilding the interface after the schema freeze — which is the day-9
divergence §13 warns about.

---

## 4. Decisions recorded

- **DEC-001 — Python-only for now, all three languages later.**
  Owner's call, this session. CLAUDE.md's standing rule is that shared-logic
  changes land in Go, Python, and TypeScript together; this deliberately
  suspends that for the framework abstraction. Recorded as a **known
  divergence**, not an accident — Go and TypeScript follow up post-hackathon.
  Consequence: the §2.3 conformance matrix must state that framework-axis rows
  are Python-only, or it will imply coverage that does not exist.

- **DEC-002 — the abstraction lives in pedro-agentware, not pedro-tag.**
  Follows from the owner's framing. Also removes the SC-002 scope conflict:
  pedro-tag stays a consumer.
  **Side effect needing attention**: SPEC.md §13's cut line lists pedro-tag
  integration at #3 as droppable, on the reasoning that "the claim survives; the
  risk doesn't." That holds only while pedro-tag is a thin consumer. It now
  is — but the framework abstraction it consumes is *not* droppable, and the
  cut line has no entry representing it. The cut line is missing a row.

---

## 5. ADK — answered

Researched this session against ADK docs and repo. Sources at the end of this
section.

### 5.1 ADK replaces the orchestration layer. It does not compose with Pydantic AI.

ADK is a full agent framework: `LlmAgent` owns the loop, and the framework
drives tool invocation. It is not an MCP substitute and not a layer you slot
under Pydantic AI — the two are alternative owners of the same loop.

**Consequence for the owner's question ("is ADK replacing MCP so I can still use
Pydantic?"): no.** But this is materially better than it sounds, because of 5.2
and 5.3.

### 5.2 ADK has exactly the pre/post tool hooks agentware needs

`LlmAgent` takes six callbacks as constructor fields (not plugins):

| Callback | Params | Return behavior |
|----------|--------|-----------------|
| `before_tool_callback` | `tool: Tool`, `args: dict`, `tool_context: ToolContext` | return a value ⇒ **skips tool execution**, uses returned value as result |
| `after_tool_callback` | same + `tool_response: ToolResponse` | return a value ⇒ replaces the tool result |
| `before_model_callback` | `callback_context`, `llm_request: LlmRequest` | return `LlmResponse` ⇒ skips the LLM call |
| `after_model_callback` | `callback_context`, `llm_response: LlmResponse` | — |

This maps onto agentware's needs almost exactly:

- `before_tool_callback` returning a value = **the deny path.** A policy denial
  returns the denial result and the tool never runs. This is the same semantics
  as `middleware.go:51-56`.
- `after_tool_callback` = **the post-execution hook this repo does not have**
  (SC-006). It sees `tool_response`, which is where `resources_touched[]`,
  `latency_ms`, and `error` become extractable.
- `after_model_callback` sees `LlmResponse`, which is the natural place to
  capture token usage for §4's `tokens_in`/`tokens_out`/`cached_tokens`.

Python note: ADK passes callback args **by keyword**, so parameter names must
match the documented names exactly.

### 5.3 ADK is model-agnostic via model connectors

Claude, OpenAI, Ollama, vLLM are supported through wrapper classes (LiteLLM
among them) passed to `LlmAgent`. So adopting ADK does not force Gemini-only,
and the existing model-format work (§1) is not invalidated.

SPEC.md §6 stretch ("per-agent model selection", "Gemma routing") and §7's
"default must remain Gemini 3.5+ via Vertex" are both expressible here.

### 5.4 Revised recommendation: tool-layer, not the §12 transport fallback

SPEC.md §12's fallback — "wrap ADK at the transport layer rather than the tool
layer — less elegant, still satisfies the framework requirement" — was written
against an assumed risk that tool-layer interception would be deep. Given 5.2 it
is not: the hooks are first-class constructor fields with documented
skip-execution semantics. **Tool-layer is now the cheaper path as well as the
better one**, and the transport fallback should be treated as dead unless the
callbacks disappoint in practice.

Caveat to verify before relying on it: a known ADK issue reports that
`before_tool_callback`/`after_tool_callback` are **not fired during live
(streaming) tool execution** — `_execute_single_function_call_live()` calls agent
callbacks but skips plugin-manager callbacks. If the demo path uses live
streaming, this is a hole in "intercepts *every* tool call." Test explicitly on
day 5.

### 5.5 What this does to the abstraction in §2

The `AgentBackend` sketch survives, with a clarified division:

- **ADKBackend** — thin. Constructs `LlmAgent` with agentware's policy check
  wired to `before_tool_callback` and audit emission split across
  `after_tool_callback` (result, resources, latency) and `after_model_callback`
  (tokens). ADK owns the loop.
- **PydanticAIBackend** — wraps the existing path, which owns its own loop.

Both emit the same `AuditRecord`. The two backends differ in *who drives*, which
is precisely the framework axis §1 defines — and the reason a shared interface is
needed rather than just a shared formatter.

### 5.6 Note on SC-007 sequencing

`after_tool_callback` gives ADK a post-execution seam that the native path lacks
(SC-006). If SC-007 is not fixed first, the ADK backend can populate
`resources_touched[]`/`latency_ms`/tokens and the Pydantic backend cannot — a
field-population divergence between backends, which is exactly the §2.3 Audit
invariant failing. Confirms the owner's call that SC-007 leads.

**Sources**: [google/adk-python](https://github.com/google/adk-python) ·
[Types of callbacks](https://adk.dev/callbacks/types-of-callbacks/) ·
[Models](https://adk.dev/agents/models/) ·
[Issue #4704 — live tool execution skips callbacks](https://github.com/google/adk-python/issues/4704)

---

## 6. What deterministic parity will mean, once the above exists

Restating §2.3's four invariants against the real code, so the matrix has
concrete cells:

| Dimension | Concrete test | Blocked on |
|-----------|---------------|------------|
| Schema | One tool def renders to a valid call for each model format *and* each framework backend | Framework abstraction (§2) |
| Marshalling | Golden inputs — nullables, enums, nested objects — produce identical executed calls across backends | Framework abstraction; also **D-001 must be fixed first**, since TypeScript's filter path already diverges |
| Policy | Same policy, same subject, same allow/deny across backends | Framework abstraction + SC-010 (nothing currently requires the middleware to be in the path) |
| Audit | Same fields populated with same semantics across backends | SC-007 → SC-008 |

Every row is blocked on work in §3. None of the four can be tested today.
