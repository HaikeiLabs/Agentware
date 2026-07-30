# Wiki Memory — Build Log

## [2026-07-30] 4.1+4.2 TypeScript SDK + cross-SDK isolation | DONE
`typescript/src/memory`: async WikiMemory MCP stdio client (spawns memctl
serve per user; pending-FIFO correlation; same surface as Python minus
inference), parseDiagnostics, and memoryTools() in the Vercel AI SDK tool
shape (zod parameters; denies render as "DENIED: ..." for
self-correction). Jest: 5 new tests incl. cross-SDK — a page written via
the Python SDK is queryable via the TS SDK for the same user and invisible
(empty query + claims) for another user. tsc build green, 131 TS tests
pass. Note: `npm run lint` is broken pre-existing (direct minimatch@10.2.3
pin shadows eslint 8's CJS minimatch) — untouched by this work.

## [2026-07-30] 3.3 dogfood: enforced ingest → contradiction → inference | DONE
Schema gains claim-to-claim refs (claims[].supports/contradicts, "c2" or
"page#c2") — parsed in Go, surfaced by memory_get_claims, documented in
SCHEMA.md. Python glue pedro_agentware.memory.confidence builds the
inference request from vault claims and merges marginals back.
examples/wiki_memory_dogfood.py drives the LangGraph tool surface against
the real Go core: 3 overlapping sources ingested; first page write DENIED
(twitch:Golang, unknown-concept) and self-corrected to twitch:Go from the
nearest-term diagnostics (deny→retry logged); 4th contradicting source
recorded; inference run and confidence written back through the enforced
path. Results: c1 0.962→0.941 (drops), contrarian c3 0.211 with
contested=true, all via belief propagation. Suite: 119 python + all Go
green; ruff + mypy strict clean.

## [2026-07-30] 3.2 pgmpy inference engine + JSON contract | DONE
Contract at go/memory/infer/schema.json (one schema for subprocess and
future MCP transports). Engine at pedro_agentware.memory.infer (pgmpy
DiscreteMarkovNetwork; 'inference' extra; runnable via python -m for the
Go subprocess transport): binary claim/source nodes, agreement/
disagreement potentials (supports 0.8, contradicts 0.9, sourceOf 0.85),
source priors 0.7 default / 0.4 superseded, BP first with Gibbs fallback,
contested = contradicts edge vs claim above 0.6. Tuned sourceOf from 0.7
to 0.85 after numeric probing (mutual-support case peaked at 0.74
otherwise); edge-less sources dropped so BP's junction tree stays
connected. Spec tests: mutual 0.877 (>0.85), superseded+contradicted
0.223 (<0.5, contested), cycle exact via BP. Full python suite 118 pass
(pytest -p pytest_asyncio.plugin under uv py3.12 venv).

## [2026-07-30] 3.1 Python SDK WikiMemory + LangGraph tools | DONE
`pedro_agentware.memory`: WikiMemory spawns `memctl serve` per user (MCP
stdio, per SDK plan subprocess mode), implements the SDK's ToolExecutor
protocol so it composes into MiddlewareImpl; native API (ingest,
write_page, query, get_claims, lint), parse_diagnostics for the DENY
payload; LangGraphMemoryTools exposes the five tools as plain callables
(denies render as "DENIED: ..." with diagnostics so agents self-correct).
Tests build the real Go binary and exercise round-trip, deny diagnostics,
cross-user isolation. Go executor now emits [] not null for empty results.
ruff + mypy --strict clean.

## [2026-07-30] 2.x MCP stdio server + memctl serve | DONE
`go/mcp`: minimal MCP server (JSON-RPC 2.0 newline-delimited over any
reader/writer; initialize, ping, tools/list, tools/call) serving a
tools.ToolRegistry with a fixed CallerContext — one process per principal,
matching the SDK plan's subprocess mode; scope can't be overridden in-band.
`memctl serve -root -tbox -user` wires WikiMemory behind it. Policy denies
surface as MCP tool errors with the diagnostics payload intact. Tests cover
list/call round-trip, deny-with-diagnostics, unknown method/tool; smoke:
piped JSON-RPC ingest landed in the vault. Closes the missing-MCP watch
item for the stdio transport (HTTP+SSE still future).

## [2026-07-30] 2.2+2.3 executor, chain wiring, isolation tests | DONE
`go/memory`: Executor (five tools over the per-user vault, every path
re-checked against the vault boundary, index/log maintenance, v1 keyword
query, claims listing, vault lint incl. dangling links) implementing both
ToolExecutor and VaultReader; WikiMemory Enable(Config) wiring
NewMiddleware(exec).WithPolicy(OntologyEvaluator).WithAuditor(...);
RegisterTools for the tool registry. Added exported
middleware.CallerFromContext (in-repo API gap — executors couldn't read
the caller). Chain tests: valid write persists + index/log update; deny
carries diagnostics AND lands in auditor; cycle via real vault denied;
anonymous denied; cross-user isolation (policy deny on scope-override arg,
scoped query/claims, path rejection). Note: the repo has no MCP server
package yet — tools are registry-registered; MCP exposure rides the SDK
transport work.

## [2026-07-30] 2.1 OntologyEvaluator + declarative policy | DONE
`go/memory`: two-tier evaluator implementing middleware.PolicyEvaluator —
tier 1 embedded policy.yaml (deny-by-default, scope-override + anonymous
denies, per-user+tool rate limits via middleware.RateLimiter, since the
stock engine matches MaxRate but doesn't enforce it); tier 2 semantic
validation of write content (page contract, T-box, vault-graph SKOS checks
via VaultReader — cycle-introducing write denied). DENY reasons embed JSON
diagnostics after a "diagnostics: " marker; ParseDiagnostics round-trips
them for agent self-correction. 9 new tests, module green.

## [2026-07-30] 1.3 thesaurus fixture gate | DONE
Fixture tests: full_skos + transitive_broader pass, cycle_detection +
inconsistency_broader_narrower rejected with diagnostics, symmetric_related
symmetry inferred (idempotent), cycle-safe TransitiveBroader closure added.
The gate exposed an upstream bug: ontology-go's inconsistent-hierarchy
check tested the inverse direction (false positives on full_skos, false
negative on the inconsistency fixture). Fixed upstream per loop rules —
ontology-go PR #18 — and pinned go.mod to the fix commit (BLOCKERS.md).

## [2026-07-30] 1.2 T-box validation rules + memctl lint | DONE
`go/memory/ontology`: TBox loader (classes, properties w/ domain+range,
SKOS concepts, label index) over ontology-go's ttl parser; ValidatePage
(class/property/concept existence, domain/range with transitive subclass,
unknown-prefix) returning structured Violations with nearest-term
suggestions (Levenshtein); CheckSKOSGraph wrapping ontology-go validate
(cycles, broader/narrower inconsistency); InferSymmetricRelated.
CI consumer: `go/cmd/memctl` `lint` subcommand (maintainer approved CLI
tooling for this). Smoke test: bad page → 2 violations w/ suggestions,
exit 1. Tests green against real T-box submodule.

## [2026-07-30] 1.1 page parser → A-box | DONE
`go/memory/page`: YAML frontmatter parser (strict fields, kebab-case ids,
CURIE types/preds, unique claim ids), typed-wikilink extraction
(`[[t|pred=...]]` + bare → skos:related), A-box emission as N-Triples.
Mid-iteration pivot on maintainer direction: RDF layer switched from
knakk/rdf to `github.com/soypete/ontology-go` (D5 in DECISIONS.md) — its
validate/reasoner packages also cover much of task 1.2. Tests green.

## [2026-07-30] 0.2 skeleton + vault + schema | DONE
Added `ontologies/` submodule, `go/memory/` package (doc.go + Vault with
per-user layout, kebab-case page ids, and path-boundary containment —
defense-in-depth half of user isolation), root `SCHEMA.md` (frontmatter
contract, prefixes, typed-link syntax, ingest workflow) and
`SCHEMA_GAPS.md`. `go test ./...` and `go vet ./...` green.

## [2026-07-30] 0.1 placement + RDF spike | DONE
Spiked `deiu/rdf2go` vs `knakk/rdf` against the real T-box
(`TBOX_LEARNING_SOFTWARE.ttl`, 671 triples) and three thesaurus fixtures —
both parsed all files identically. Chose `knakk/rdf` (zero deps,
deterministic streaming decode, typed terms). Placement: in-monorepo
(`go/memory/` + SDK mirrors). Recorded D1–D4 in `DECISIONS.md`; created
`PROGRESS.md` and this log.
