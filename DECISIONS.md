# Wiki Memory — Decisions

Decision log for the ontology-constrained wiki memory component. One entry per
decision; newest at the bottom.

## D1: Placement — in-monorepo (`go/memory/`)

**Decision:** Wiki memory lives in this monorepo as `go/memory/` (Go core),
`python/src/pedro_agentware/memory/` (Python SDK), and
`typescript/src/memory/` (TypeScript SDK). No companion repo.

**Why:**
- The SDK plan (`business/SDK_PLAN.md`) makes the Go module the engine and the
  Python/TS packages clients. Memory enforcement composes directly with
  `middleware.NewMiddleware(exec).WithPolicy(...).WithAuditor(...)` and
  implements the existing `middleware.PolicyEvaluator` interface — a companion
  repo would need version-locked imports of those interfaces and would churn on
  every middleware change.
- Composable components in this repo already live together (guardrails,
  toolformat, adapters); memory is another composable option, not a product.
- CI is already path-filtered per language (`.github/workflows/*-test.yml`),
  so memory changes ride the existing pipelines.

**Trade-off accepted:** the monorepo grows; mitigated by memory being a
self-contained package with no imports from it into the existing core.

## D2: Go RDF library — `knakk/rdf`

**Spike:** parsed `education/TBOX_LEARNING_SOFTWARE.ttl` (671 triples),
`thesaurus/full_skos.ttl` (75), `thesaurus/cycle_detection.ttl` (9), and
`social/twitch_topics.ttl` (121) with both candidates. Both parsed everything
without error and agreed on triple counts.

**Decision:** `github.com/knakk/rdf`.

**Why:**
- **Zero transitive dependencies** — pure stdlib. `deiu/rdf2go` pulls in
  `linkeddata/gojsonld` and `rychipman/easylex` (both unmaintained since 2017).
  Loop rule: "Go stdlib + one RDF lib" — knakk is exactly that.
- **Deterministic, streaming decode** — `NewTripleDecoder(r, rdf.Turtle)`
  yields triples in document order. rdf2go stores triples in a map and
  iterates in nondeterministic order, which makes golden tests flaky.
- **Typed terms** — `rdf.IRI` / `rdf.Literal` / `rdf.Blank` are distinguishable
  via `Term.Type()`; rdf2go stringifies terms, which loses the IRI/literal
  distinction we need for domain/range checks.
- We need our own indexed graph (subject → predicate → objects) for T-box
  lookups anyway, so rdf2go's built-in graph container adds nothing.

**Consequence:** `go/memory/` builds a small internal graph index on top of
knakk's triple stream; the T-box loader is read-only.

## D3: Ontology distribution — git submodule at `ontologies/`

**Decision:** vendor `github.com/Soypete/ontologies` as a git submodule at the
repo root (`ontologies/`). The T-box path is a *parameter* of `WikiMemory`
(default points at the submodule), so users can supply their own T-box without
forking. The T-box is read-only; gaps go to `SCHEMA_GAPS.md`, never invented
terms.

## D4: Inference transport — subprocess with JSON contract first

**Decision:** the Go core invokes the Python inference engine (pgmpy) as a
subprocess speaking the JSON contract in `go/memory/infer/schema.json`
(nodes + typed edges + weights in; per-claim marginals + `contested` flags
out). The same contract is reusable over an MCP tool call later; subprocess
first because it needs zero deployment topology and matches the SDK plan's
"spawn as subprocess — zero config" mode.
