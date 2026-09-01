# Build history

Working files from the wiki-memory build loop (2026-07-30, 15 iterations).
Archived here rather than deleted: they record why the component is shaped the
way it is, which the code alone does not explain.

These are historical. They are not maintained and may not reflect current code.

| File | What it is |
|------|-----------|
| `DECISIONS.md` | Decision log — one entry per decision, oldest first. The most useful of these files: it explains *why*, not just *what*. |
| `BUILD_LOG.md` | Iteration log from the build loop |
| `PROGRESS.md` | Phase checklist, complete |
| `BLOCKERS.md` | Blockers hit during the build and how they were routed around |
| `REPORT.md` | Final build report — component summary, fixture pass table, known gaps |

Current documentation lives in:

- `SCHEMA.md` (repo root) — the wiki-memory page contract: frontmatter, typed
  wikilinks, ingest workflow
- `SCHEMA_GAPS.md` (repo root) — **active**: ontology terms the T-box lacks.
  Add entries here rather than inventing terms locally.
- `docs/engineering-design.md`, `docs/middleware-llm-guide.md`
- `go/memory/doc.go` — package documentation
