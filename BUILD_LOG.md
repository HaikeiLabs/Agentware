# Wiki Memory — Build Log

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
