# Wiki Memory — Progress

State file for the wiki-memory build loop. One checkbox per iteration.
Phases from the loop prompt; see `DECISIONS.md` for decisions,
`BUILD_LOG.md` for the iteration log, `BLOCKERS.md` for blockers.

## Phase 0 — Scaffold + decisions
- [x] Placement decision (in-monorepo) + Go RDF lib spike (knakk/rdf) → `DECISIONS.md`
- [x] `memory/` package skeleton, per-user vault layout, `SCHEMA.md`, `SCHEMA_GAPS.md`, ontologies submodule

## Phase 1 — Validation core (shared package)
- [ ] Frontmatter + typed-wikilink parser → N-Triples (A-box)
- [ ] T-box validation rules (class/predicate existence, domain/range, SKOS acyclicity + broader/narrower consistency) as ONE package with two consumers (OntologyEvaluator + CI check)
- [ ] Fixture tests per the thesaurus files (pass full_skos + transitive_broader; reject cycle_detection + inconsistency_broader_narrower with diagnostics; infer symmetry from symmetric_related)

## Phase 2 — Middleware integration (Go core)
- [ ] `OntologyEvaluator` implementing `PolicyEvaluator`; declarative policy YAML (deny-by-default, user-scope rule, rate limits)
- [ ] Memory executor wired via `NewMiddleware(exec).WithAuditor(...)`; MCP tools registered (memory_ingest, memory_write_page, memory_query, memory_get_claims, memory_lint)
- [ ] Tests: valid write → ALLOW; unknown class → DENY + nearest-term diagnostic; cycle-introducing link → DENY; denies audited; user A cannot touch user B's vault (policy AND path check)
- [ ] agentware API gaps → upstream issue/PR, noted in `BLOCKERS.md`

## Phase 3 — Python SDK + inference
- [ ] `WikiMemory` enablement in Python SDK (composable option, user scope from CallerContext), LangGraph integration exposing memory tools
- [ ] pgmpy inference engine + JSON contract; unit tests (mutual support > 0.85; contradicted+superseded < 0.5 and contested; convergence or Gibbs fallback on cycle)
- [ ] Dogfood: LangGraph agent ingests 3 overlapping sources + 1 contradicting source; confidence drops, flag sets, deny→retry logged

## Phase 4 — TypeScript SDK
- [ ] Enablement surface + MCP client parity with Python (minus inference); one TS framework integration example
- [ ] Cross-SDK test: page written via Python SDK readable via TS SDK for same user, invisible for different user

## Phase 5 — Query, lint, report
- [ ] `memory_query` answers L2WS competency questions + contested claims + low-confidence claims
- [ ] `memory_lint`: orphan pages, pageless concepts, stale pages, missing typed links
- [ ] E2E in CI: fresh clone → enable memory → ingest → infer → query, green
- [ ] `REPORT.md`
