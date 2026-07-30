# Wiki Memory — Build Report

Ontology-constrained wiki memory for pedro-agentware: an LLM-maintained,
per-user markdown wiki with T-box enforcement on every write and a Markov
link network for claim confidence. Built 2026-07-30 across 15 loop
iterations; every phase of the plan is complete.

## What was built

**Go core (`go/memory`, `go/mcp`, `go/cmd/memctl`)** — the engine:

- `memory.Vault` — per-user vault layout (`<root>/<user>/wiki/` + `raw/`)
  with kebab-case ids and path-boundary containment.
- `memory/page` — frontmatter + typed-wikilink parser
  (`[[t|pred=sw:buildsToward]]`, bare `[[t]]` → skos:related), claim
  supports/contradicts refs, A-box emission as N-Triples.
- `memory/ontology` — ONE validation package with two consumers
  (evaluator + `memctl lint`): T-box loading via
  `github.com/soypete/ontology-go`, class/property/concept existence,
  domain/range over transitive subclass, SKOS cycle and
  broader/narrower-consistency checks, nearest-term suggestions
  (Levenshtein), SKOS label→concept matching for ingest.
- `memory.OntologyEvaluator` — implements the stock
  `middleware.PolicyEvaluator`. Tier 1: embedded declarative
  `policy.yaml` (deny-by-default, scope-override and anonymous denies,
  per-user+tool rate limits). Tier 2: semantic validation of page writes,
  including graph checks against the caller's existing vault
  (cycle-introducing writes denied). DENY reasons embed a JSON
  diagnostics payload agents parse to self-correct.
- `memory.Enable(Config)` — the composable enablement:
  `NewMiddleware(exec).WithPolicy(evaluator).WithAuditor(auditor)`; five
  tools (`memory_ingest`, `memory_write_page`, `memory_query`,
  `memory_get_claims`, `memory_lint`) registered on the tool registry.
  Every decision audited; user scope comes only from `CallerContext`
  (policy AND path check — defense in depth, tested both ways).
- `go/mcp` + `memctl serve` — minimal MCP stdio server (JSON-RPC 2.0)
  exposing any tool registry with a fixed per-process principal; the SDK
  transport per `business/SDK_PLAN.md`. `memctl lint` is the CI/dev
  consumer of the validation rules.
- `memory_query` competency questions: transitive prerequisites,
  builds-toward, learning path to a role (topologically ordered),
  contested claims, low-confidence claims. `memory_lint`: ontology +
  graph checks plus orphan pages, dangling (pageless) targets, stale
  pages, missing typed links.

**Python SDK (`pedro_agentware.memory`)** — client + inference:

- `WikiMemory` spawns `memctl serve` per user over MCP stdio; implements
  the SDK's `ToolExecutor` protocol so it composes into `MiddlewareImpl`;
  `parse_diagnostics` for deny payloads; `LangGraphMemoryTools` exposes
  the tools to LangGraph agents (denies render as `DENIED: ...`).
- `memory.infer` (pgmpy, `inference` extra, uv/py3.12) — the Markov link
  network per `go/memory/infer/schema.json`: binary claim/source nodes,
  supports 0.8 / contradicts 0.9 / sourceOf 0.85 potentials, source
  priors 0.7 (0.4 superseded), belief propagation with Gibbs fallback,
  `contested` flags. Runnable as a subprocess (`python -m`).
- `memory.confidence` — builds inference requests from vault claims and
  merges marginals back for write-back through the enforced path.
- Dogfood (`examples/wiki_memory_dogfood.py`, tested): 3 overlapping
  sources ingested; a write denied for `twitch:Golang` self-corrects to
  `twitch:Go` from the diagnostics; a 4th contradicting source drops the
  claim 0.962→0.941 and flags the contrarian claim contested at 0.211;
  confidence written back; queries reflect the inferred state.

**TypeScript SDK (`typescript/src/memory`)** — async `WikiMemory` MCP
client (parity minus inference), `parseDiagnostics`, and `memoryTools()`
in the Vercel AI SDK tool shape (zod parameters). Cross-SDK test: a page
written via the Python SDK is queryable via the TS SDK for the same user
and invisible to another user.

**CI** — `.github/workflows/memory-e2e.yml`: fresh clone with submodules
→ Go tests → memctl lint → Python suite with inference → dogfood chain →
TS suite. All steps verified locally.

## Fixture gate (thesaurus)

| Fixture | Required behavior | Result |
|---|---|---|
| `full_skos.ttl` | pass clean | PASS (after upstream fix, see gaps) |
| `transitive_broader.ttl` | pass; selfPaced closes to course | PASS |
| `cycle_detection.ttl` | reject with diagnostics; traversal terminates | PASS (skos-cycle, subjects named) |
| `inconsistency_broader_narrower.ttl` | reject with diagnostics | PASS (skos-inconsistent-hierarchy) |
| `symmetric_related.ttl` | infer symmetry, idempotent | PASS |

Inference spec tests: mutual support from reliable sources → 0.877 both
(> 0.85); contradicted claim from superseded source → 0.223 (< 0.5) and
contested; support cycle → exact via belief propagation.

## Known gaps

- **ontology-go PR #18 — merged.** The fixture gate exposed an inverted
  direction check in upstream's inconsistent-hierarchy validation (false
  positives on valid inverse pairs, false negative on the real
  contradiction). Fixed upstream with regression tests
  (https://github.com/Soypete/ontology-go/pull/18, merged 2026-07-30);
  `go.mod` tracks upstream main again.
- **MCP transport is stdio-only** — one `memctl serve` process per
  principal. The SDK plan's HTTP+SSE sidecar mode (multi-user, caller
  identity per request) is not built.
- **Supersedes has no on-disk syntax** — the inference contract and
  engine support `supersedes`, but raw sources carry no metadata file, so
  supersession is passed explicitly to `build_inference_request`.
- **Hand-set weights** — potentials are config, not learned; no MLN
  grounder in v1 (as planned). Weight learning is future work.
- **Inference is caller-orchestrated** — the Go core does not yet invoke
  the Python engine itself; the SDK (or agent) runs infer and writes back
  through the enforced path. The JSON contract is transport-ready.
- Pre-existing repo issues, untouched: `npm run lint` broken by a direct
  `minimatch@10` pin shadowing eslint's; `tests/adapters` style
  violations (CI lints `src/` only); `SCHEMA_GAPS.md` is empty — the
  L2WS T-box covered everything the dogfood needed.

## Three recommendations for v2

1. **HTTP+SSE MCP sidecar with per-request principals.** The per-user
   subprocess model is right for dev and single-agent use, but a shared
   deployment needs one server that derives `CallerContext` from
   authenticated request metadata — then the same policy tier serves
   many users, and the inference engine can be invoked server-side after
   each write instead of by the client.
2. **Close the ingest→page loop with SKOS label matching.** The T-box
   label index (`MatchConceptLabel`, "Golang" → `twitch:Go`) is built
   but memory_ingest doesn't use it yet: v2 should propose topic tags
   and typed-link candidates at ingest time, turning deny→retry cycles
   into pre-corrected first writes, and add source metadata (reliability,
   supersedes) as a small frontmatter block on `raw/` files.
3. **Learn edge weights from vault history.** Every decision is audited
   and confidence is versioned in git-friendly markdown; that history is
   training data. Start with per-source reliability estimated from how
   often a source's claims end up contested or reverted, before
   attempting full MLN weight learning.
