# Wiki Memory — Page Schema & Maintainer Instructions

This is the contract for pages in a wiki-memory vault. The
`OntologyEvaluator` enforces it on every write; agents maintaining a vault
should follow it to avoid deny→retry cycles.

## Vault layout (one per user)

```
<memory_root>/<user_id>/
├── wiki/
│   ├── index.md          # table of contents, maintained on every write
│   ├── log.md            # append-only maintenance log
│   └── <page-id>.md      # typed pages (kebab-case ids)
└── raw/                  # ingested source material (read-only after ingest)
```

User scoping is absolute: tools resolve the vault from the caller's
`CallerContext`; cross-user reads and writes are denied by policy and by a
path-boundary check.

## Frontmatter contract

Every page under `wiki/` (except `index.md` and `log.md`) starts with YAML
frontmatter:

```yaml
---
id: go-worker-pools            # kebab-case, unique per user vault, == filename
type: sw:Skill                 # CURIE of a class from the T-box (required)
labels: ["Worker Pools", "worker pool pattern"]
topics: [twitch:Go, twitch:Concurrency]   # SKOS concepts from twitch_topics.ttl
links:
  - {pred: sw:requiresPrerequisite, target: goroutines}
  - {pred: skos:related, target: channels}
claims:
  - {id: c1, text: "Bounded worker pools prevent goroutine leaks under load",
     sources: [src-pprof-talk], confidence: null}   # confidence written by inference, never by hand
sources: [src-pprof-talk, src-go-blog-pipelines]
updated: 2026-07-30
---
```

Rules:

- `id` — kebab-case (`^[a-z0-9]+(-[a-z0-9]+)*$`), unique in the vault, must
  equal the filename without `.md`.
- `type` — a CURIE naming a class that exists in the T-box. Unknown classes
  are DENIED; the diagnostic lists nearest valid terms. If no class fits,
  add an entry to `SCHEMA_GAPS.md` — never invent terms.
- `links[].pred` — a property from the T-box with compatible domain/range
  for the source and target page types. `links[].target` is a page id in
  the same vault.
- `claims[].id` — unique within the page; referenced by the inference
  engine. `confidence` is owned by inference (leave `null` on write);
  `contested: true` is set when a confident opposing claim exists.
- `claims[].supports` / `claims[].contradicts` — optional lists of claim
  references: `c2` for a claim in the same page, `other-page#c1` across
  pages. These become the `supports`/`contradicts` edges of the Markov
  link network.
- `sources` — ids of entries under `raw/`.
- `updated` — ISO date of last substantive edit.

## Prefixes

| Prefix   | Namespace                              | Source                                  |
|----------|----------------------------------------|-----------------------------------------|
| `sw:`    | `http://soypete.tech/l2ws/`            | `ontologies/education/TBOX_LEARNING_SOFTWARE.ttl` |
| `twitch:`| `http://soypete.tech/twitch/topics/`   | `ontologies/social/twitch_topics.ttl`   |
| `skos:`  | `http://www.w3.org/2004/02/skos/core#` | SKOS core                               |

## Typed links in prose

- `[[target|pred=sw:buildsToward]]` — typed wikilink.
- `[[target]]` — bare link, defaults to `skos:related`.

Both forms are extracted and validated exactly like frontmatter `links`.

## Ingest workflow

1. Store the source verbatim under `raw/` with an id (`src-...`).
2. Match topics against SKOS prefLabel/altLabel (e.g. "Golang" → `twitch:Go`).
3. Create or update pages through `memory_write_page` (the enforced path —
   never write files directly). On DENY, read the structured diagnostics,
   correct the page, and retry.
4. Record claims with their sources; leave `confidence` null.
5. Update `index.md` and append a line to `log.md`.
6. Run `memory_lint` and fix what it reports.

## The T-box is read-only

Missing classes or predicates are recorded in `SCHEMA_GAPS.md` at the repo
root. The ontology is a parameter of `WikiMemory` — this repo's vendored
`ontologies/` submodule is the default, but any T-box with the same shape
can be supplied.
