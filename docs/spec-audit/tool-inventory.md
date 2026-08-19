# tool-inventory

Tools currently defined, their schema, and which adapters render them.
SPEC.md §13 day-0 output 1.

Verified against `/Users/soypete/code/pedro/pedro-tag` (read this session).
Citations are pedro-tag-relative unless prefixed.

---

## Where tools live

**pedro-agentware defines no concrete tools.** It holds a registry and executor
for caller-supplied tools (`go/tools/registry.go`, `go/tools/executor.go`) plus
the model-format layer. Confirms G-025 and DEC-008.

**pedro-tag holds the templates**, in
`src/pedro_service/tool_definitions.py` (596 lines).

## Template shape — answers open interface question 1

Templates are **pure data. No execution logic, no handler references.**

```python
@dataclass
class ToolParameter:            # tool_definitions.py:21-27
    name: str
    type: str
    description: str
    required: bool = False
    default: Any = None
    enum: Optional[List[str]] = None

@dataclass
class ToolDefinition:           # tool_definitions.py:31-36
    name: str
    description: str
    parameters: list[ToolParameter]
    permission: str
    categories: list[str] = field(default_factory=list)
```

**So agentware's new tool object is a renderer, not a loader.** That is the
simpler of the two shapes in `parity.md` §2a and it settles that question.

`TOOL_DEFINITIONS` (`tool_definitions.py:38`) is a module-level list of these.

## The `permission` field — a third policy vocabulary

Every template carries `permission: str` (`tool_definitions.py:35`) and there is
a lookup helper `get_tools_by_permission` (`tool_definitions.py:589-591`).

Observed values: `search_wiki`, `web_search`, `schedule_meetings`.

This is a **capability name attached to the tool**, not a rule and not a
decision. It is a third vocabulary alongside:

| Repo | Vocabulary | Location |
|---|---|---|
| pedro-tag | per-tool `permission` capability names | `tool_definitions.py:35` |
| agentware | `allow` / `deny` / `filter` | `pedro-agentware:go/middleware/types.go:7-11` |
| kei | `permit` / `deny` / `enrollment_required` | `kei:cmd/proxy/authorize.go:63,105,110` |

The new tool object will carry `permission` across the boundary, so the schema
freeze needs to say what it maps to — a policy rule input, an ABAC action, or
metadata. **Rule 3 flag: extends G-044 from two vocabularies to three.**

## Model-format renderers — the axis that already works

`render_tools(tools, format)` (`tool_definitions.py:527-546`) dispatches to:

| Format | Renderer | Output shape |
|---|---|---|
| `OPENAI` | `render_openai_tools` (`:459`) | `{"type":"function","function":{name,description,parameters}}` |
| `ANTHROPIC` | `render_anthropic_tools` (`:492`) | `{name,description,input_schema}` |
| `OLLAMA` | `render_ollama_tools` (`:522`) | delegates to OpenAI renderer |
| `LLAMA` | → `render_openai_tools` | same as OpenAI |
| `VLLM` | → `render_openai_tools` | same as OpenAI |

Plus `detect_model_format` (`:565-578`), substring matching on the model name.

This is the **model axis** of `parity.md` §1 and it is real, working, and
directly comparable to agentware's Go `toolformat/`. Note three of five formats
are the same renderer, so the matrix has three distinct output shapes, not five.

## The gap: templates are not wired to the agent

`grep -rn "TOOL_DEFINITIONS|render_tools|get_tools_for_model|get_tools_by_permission"`
across `pedro-tag/src/` returns **no consumers outside `tool_definitions.py`
itself.**

The live agent registers tools a different way — as decorated Pydantic AI
functions with hand-written signatures: `search_wiki` (`agent.py:298`),
`web_search` (`agent.py:338`), `respond_tool` (`agent.py:384`),
`start_game_tool` (`agent.py:1216`), on an `Agent(...)` built at
`agent.py:1403`.

And permissions are enforced by `check_permission` (`agent.py:184-205`), which
tests membership in `context.deps.permissions` — a `set[Permission]` on
`AgentDeps` (`agent.py:179`) — and raises `PermissionError`. That is a separate
enum from the templates' `permission: str`, checked inside each tool body rather
than at a boundary.

**Consequences:**

1. The templates are currently a **parallel, unused definition** of the tools.
   They are a clean starting point precisely because nothing depends on them —
   but "generic templates the agents use" is not the current state; the agents
   use hand-written duplicates.
2. Template ↔ live-tool drift is unchecked. Any conformance matrix built from
   `TOOL_DEFINITIONS` describes the templates, not what the agent actually runs,
   until they are wired together.
3. pedro-tag's real enforcement is `check_permission` inside tool bodies
   (`agent.py:190`) — per-tool, in-agent, not middleware. This is SC-001's
   "per-agent call" architecture, now confirmed in code rather than inferred
   from the integration prompt.

## Inventory

From `TOOL_DEFINITIONS`. Partial — the file is 596 lines and was read in
sections; entries below are confirmed by direct citation.

| Tool | Params (req'd*) | `permission` | Categories | Live equivalent |
|---|---|---|---|---|
| `search_wiki` (`:40`) | `query*` | `search_wiki` | memory, context | `agent.py:298` |
| `web_search` (`:54`) | `query*`, `max_results`=5 | `web_search` | information, search | `agent.py:338` |
| `schedule_meeting` (`:74`) | `title*`, `datetime*`, `attendees`, `description` | `schedule_meetings` | calendar, scheduling | not found |
| `list_prs` (`:110`) | — | — | — | not read |

Remaining entries between `tool_definitions.py:110` and `:459` not yet
enumerated.

## Adapter matrix status

The framework axis (`adapter-matrix.md`) has **no rows yet**: no ADK backend
exists, and the Pydantic path uses hand-written tools rather than templates. The
model axis above is the only populated half.
