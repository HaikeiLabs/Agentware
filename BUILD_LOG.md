# Wiki Memory — Build Log

## [2026-07-30] 0.1 placement + RDF spike | DONE
Spiked `deiu/rdf2go` vs `knakk/rdf` against the real T-box
(`TBOX_LEARNING_SOFTWARE.ttl`, 671 triples) and three thesaurus fixtures —
both parsed all files identically. Chose `knakk/rdf` (zero deps,
deterministic streaming decode, typed terms). Placement: in-monorepo
(`go/memory/` + SDK mirrors). Recorded D1–D4 in `DECISIONS.md`; created
`PROGRESS.md` and this log.
