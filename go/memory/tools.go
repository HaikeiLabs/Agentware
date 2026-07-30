package memory

// Memory tool names. These are the MCP tool identifiers served by the Go
// core; the declarative policy and the OntologyEvaluator key off them.
const (
	ToolIngest    = "memory_ingest"
	ToolWritePage = "memory_write_page"
	ToolQuery     = "memory_query"
	ToolGetClaims = "memory_get_claims"
	ToolLint      = "memory_lint"
)

// Tools lists every memory tool name.
func Tools() []string {
	return []string{ToolIngest, ToolWritePage, ToolQuery, ToolGetClaims, ToolLint}
}

// isSemanticWrite reports whether a tool's args carry wiki-page content
// subject to ontology validation. memory_ingest stores raw source text
// verbatim, so only page writes get the semantic tier; both pass the
// declarative tier and are audited.
func isSemanticWrite(name string) bool {
	return name == ToolWritePage
}
