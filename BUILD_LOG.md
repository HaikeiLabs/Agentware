# Wiki Memory — Build Log

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
