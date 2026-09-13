# Wiki Memory — Blockers

Active blockers and how they were routed around. Resolved items move to the
bottom.

## Watching (not blocking)

(none)

## Resolved

- **ontology-go PR #18** (inverted inconsistent-hierarchy check) —
  merged 2026-07-30; `go/go.mod` re-pinned to main
  (`v0.0.0-20260730193222-0c5ba6ae2cd5`), all tests green.
- **No MCP server package in agentware** — resolved by `go/mcp` (stdio
  JSON-RPC 2.0 server) + `memctl serve`; both SDKs consume it. HTTP+SSE
  transport remains future work (see REPORT.md v2 recommendations).
