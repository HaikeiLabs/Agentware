# Wiki Memory — Blockers

Active blockers and how they were routed around. Resolved items move to the
bottom.

## Watching (not blocking)

- **ontology-go PR #18 pending merge.**
  `validate.checkInconsistentHierarchy` had an inverted direction check
  (flagged consistent inverse pairs, missed real broader+narrower
  contradictions). Fix + regression tests submitted upstream:
  https://github.com/Soypete/ontology-go/pull/18. Until merge, `go/go.mod`
  pins the canonical module at the PR commit
  (`v0.0.0-20260730165556-4c8e635acec4`) — same module path, no fork or
  vendor patch. After merge: re-pin to main and delete this entry.
