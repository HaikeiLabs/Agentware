# Agent Middleware - Developer Guide

## Overview

This is the **agent-middleware** repository — a Go module that provides MCP-compatible middleware enforcing contracts on context, tools, and data. The middleware sits between the agent (LLM orchestrator) and tool execution, intercepting every tool call to enforce policies before allowing execution.

This repository is currently in the planning/engineering design phase. The actual Go implementation will be created based on the architecture defined in `business/ENGINEERING_DESIGN.md`.

---

## Project Context

This middleware integrates with:
- **PedroCLI** - Agent framework with mature tool registry and bridge patterns
- **professor_pedro** - Learning platform with orchestrator patterns
- **iam_pedro** - Bot platform with moderation and rate-limiting

Reference documents in `business/`:
- `ENGINEERING_DESIGN.md` - Core architecture and interfaces
- `CODE_EXTRACTION_PLAN.md` - What code to extract from existing repos
- `EXISTING_PATTERNS.md` - Patterns to leverage from existing codebases
- `SDK_PLAN.md` - SDK design and usage patterns
- `MILESTONE_DETAILS.md` - Implementation milestones

---

## Build, Lint, and Test Commands

### Python (pedro-agentware)

```bash
# Install dependencies
cd python && pip install -e ".[dev]"

# Run linter
ruff check .

# Run type checker
mypy .

# Run all tests
pytest

# Run a single test
pytest -k TestName

# Run with verbose output
pytest -v

# Format code
ruff format .
```

### Go (middleware)

```bash
# Build the module
go build ./...

# Run all tests
go test ./...

# Run a single test
go test -run TestName ./...

# Run with verbose output
go test -v -run TestName ./...

# Run linter
golangci-lint run

# Format code
gofmt -w .

# Vet code
go vet ./...
```

### Testing Guidelines

- Write unit tests for all exported functions
- Use table-driven tests for functions with multiple test cases
- Mock external dependencies (Policy, Auditor, ToolExecutor)
- Test both success and failure paths
- Name test files: `*_test.go`

---

## Code Style Guidelines

### General Principles

- Write idiomatic Go — follow standard library conventions
- Keep functions small and focused (single responsibility)
- Prefer composition over inheritance
- Use interfaces for abstraction (see existing patterns in docs)

### Naming Conventions

- **Packages**: lowercase, short, e.g., `middleware`, `policy`, `audit`
- **Interfaces**: `ToolExecutor`, `Policy`, `Auditor` — noun-based, noter-like
- **Functions**: `ValidateToolCall`, `EnforcePolicy` — VerbFirst, camelCase
- **Variables**: `toolName`, `policyConfig` — camelCase, descriptive
- **Constants**: `MaxToolCallsPerMinute`, `DefaultTimeout` — PascalCase for exported, camelCase for unexported
- **Types**: `ToolDefinition`, `ToolResult` — PascalCase

### Imports

- Standard library first, then third-party, then internal
- Group imports: stdlib | external | internal
- Use explicit imports (no dot imports)
- Example:

```go
import (
    "context"
    "errors"
    "time"

    "github.com/google/uuid"
    "go.uber.org/zap"

    "middleware/internal/config"
)
```

### Formatting

- Use `gofmt` or `go fmt` — no manual formatting
- Maximum line length: 100 characters (let gofmt handle)
- Add newline between import groups
- No trailing whitespace

### Types and Interfaces

- Define interfaces early — they clarify contracts
- Use concrete types for implementation, interfaces for dependencies
- Embed interfaces rather than wrapping where possible
- Document all exported types and interfaces

Example from design docs:

```go
// ToolExecutor is the interface the middleware wraps.
// Matches PedroCLI's ToolBridge pattern.
type ToolExecutor interface {
    CallTool(ctx context.Context, name string, args map[string]interface{}) (*ToolResult, error)
    ListTools() []ToolDefinition
}
```

### Error Handling

- Return descriptive errors — include context
- Use sentinel errors for expected conditions: `ErrToolNotFound`, `ErrPolicyDenied`
- Wrap errors with `fmt.Errorf("context: %w", err)`
- Never silently ignore errors with `_`
- Handle errors at the appropriate level

### Context Usage

- Pass `context.Context` as first argument to functions that may timeout or be canceled
- Use `context.TODO()` when context is not yet available
- Set timeouts for external calls
- Check `ctx.Err()` in long-running operations

### Logging

- Use structured logging (zap or zerolog)
- Include request IDs for traceability
- Log at appropriate levels: Debug for details, Info for normal flow, Error for failures
- Don't log sensitive data (keys, tokens, passwords)

### Configuration

- Use YAML or JSON config files
- Support environment variable overrides
- Provide sensible defaults
- Validate config on startup

### Concurrency

- Use goroutines for concurrent operations
- Always use `context` for cancellation
- Use `sync.WaitGroup` or channels for synchronization
- Protect shared state with mutexes or channels
- Don't leak goroutines — ensure they can exit

### Testing Best Practices

- Test behavior, not implementation
- Use subtests for grouped test cases
- Benchmark performance-critical code
- Test edge cases and error conditions
- Keep tests fast and independent

### Documentation

- Document all exported symbols
- Use doc comments (no doc blocks for internal)
- Example: `// ToolResult represents the result of a tool execution.`
- Include usage examples for complex APIs

### Performance Considerations

- Reuse buffers where possible
- Use sync.Pool for frequently allocated objects
- Avoid unnecessary allocations in hot paths
- Profile before optimizing

---

## Key Patterns to Follow

Based on existing Pedro repos:

1. **ToolBridge Pattern**: Wrap executor with middleware interface
2. **Validation First**: Validate tool calls before execution (PedroCLI pattern)
3. **Filter Tool Definitions**: Remove tools before LLM sees them
4. **Audit Everything**: Log all decisions with full context
5. **Rate Limiting**: Track per-tool, per-user usage
6. **Config Hierarchy**: Project -> User -> Defaults

---

## Directory Structure (Proposed)

```
middleware/
├── go.mod
├── go.sum
├── middleware.go       # Core middleware implementation
├── types.go            # Core types (ToolDefinition, ToolResult)
├── executor.go         # ToolExecutor interface
├── policy/
│   ├── policy.go       # Policy interface and implementations
│   └── config.go       # Policy configuration
├── audit/
│   ├── audit.go        # Auditor interface
│   └── logger.go       # Audit logger implementation
├── context/
│   └── context.go      # Context control (trusted/untrusted)
├── data/
│   └── filter.go       # Data control (response filtering)
└── examples/
    └── main.go         # Usage examples
```

---

## Future Integration

Once implemented, this middleware will be imported by:
- `PedroCLI` — replaces existing bridge implementations
- `professor_pedro` — wraps tool execution
- `iam_pedro` — adds policy enforcement to moderation tools

Follow semantic versioning for releases.