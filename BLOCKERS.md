# Wiki Memory — Blockers

Active blockers and how they were routed around. Resolved items move to the
bottom.

## Watching (not blocking)

- **No MCP server package in agentware yet.** `business/SDK_PLAN.md`
  specifies an `mcp/` package (stdio + HTTP transports) that doesn't exist;
  memory tools are currently exposed via `tools.ToolRegistry` and
  `WikiMemory.RegisterTools`. The SDK-facing MCP exposure lands with the
  Python/TS client phases; if the mcp package is still absent then, build
  the minimal server as part of that work rather than forking the plan.

- **ontology-go PR #18 pending merge.**
  `validate.checkInconsistentHierarchy` had an inverted direction check
  (flagged consistent inverse pairs, missed real broader+narrower
  contradictions). Fix + regression tests submitted upstream:
  https://github.com/Soypete/ontology-go/pull/18. Until merge, `go/go.mod`
  pins the canonical module at the PR commit
  (`v0.0.0-20260730165556-4c8e635acec4`) — same module path, no fork or
  vendor patch. After merge: re-pin to main and delete this entry.
