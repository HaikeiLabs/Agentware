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

// writeTools are the tools whose args carry page content subject to
// semantic (ontology) validation.
func isWriteTool(name string) bool {
	return name == ToolIngest || name == ToolWritePage
}
