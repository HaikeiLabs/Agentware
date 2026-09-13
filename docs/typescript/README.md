# TypeScript Middleware Usage Examples

This document provides examples of how to use the TypeScript middleware for policy enforcement.

## Installation

```bash
npm install @haikeilabs/agentware
```

## Basic Usage

### Creating a Policy

```typescript
import { Policy, Rule, Action, RateLimitConfig } from '@haikeilabs/agentware/middleware';

const policy = new Policy({
  defaultDeny: false,
  rules: [
    new Rule({
      name: 'rate-limit-tools',
      tools: ['*'],
      action: Action.ALLOW,
      maxRate: new RateLimitConfig({ count: 10, window: 60 }),
    }),
    new Rule({
      name: 'deny-admin',
      tools: ['delete_database', 'drop_table'],
      action: Action.DENY,
      conditions: [
        {
          field: 'caller.trusted',
          operator: 'eq',
          value: false,
        }
      ],
    }),
  ],
});
```

### Creating Middleware

```typescript
import { Middleware, CallerContext, ToolResult } from '@haikeilabs/agentware/middleware';

const myToolExecutor = async (toolName: string, args: Record<string, unknown>): Promise<ToolResult> => {
  // Your tool execution logic here
  return {
    toolName,
    success: true,
    result: { output: `Executed ${toolName}` },
  };
};

// Create middleware
const mw = new Middleware({
  executor: myToolExecutor,
  policy,
});

// Call a tool through middleware
const result = await mw.call('read_file', { path: '/tmp/test.txt' });
```

### Using Caller Context

```typescript
import { CallerContext } from '@haikeilabs/agentware/middleware';

// Create caller context with user information
const callerCtx = new CallerContext({
  trusted: true,
  role: 'user',
  userId: 'user-123',
  sessionId: 'session-456',
  source: 'cli',
});

// Call tool with caller context
const result = await mw.call('read_file', { path: '/tmp/test.txt' }, callerCtx);
```

### Using Audit

```typescript
import { InMemoryAuditor } from '@haikeilabs/agentware/middleware';

// Create in-memory auditor
const auditor = new InMemoryAuditor();

// Configure middleware with auditor
const mw = new Middleware({
  executor: myToolExecutor,
  policy,
  auditor,
});

// After tool calls, get audit log
const log = auditor.getLog();
for (const entry of log) {
  console.log(`Decision: ${entry.decision.action}, Tool: ${entry.toolCall.toolName}`);
}
```

## Loading Policy from YAML

```typescript
import { loadPolicyFromFile } from '@haikeilabs/agentware/middleware';

// Load policy from YAML file
const policy = loadPolicyFromFile('policy.yaml');

const mw = new Middleware({ executor: myToolExecutor, policy });
```

Example `policy.yaml`:

```yaml
rules:
  - name: "rate-limit-read"
    tools:
      - "read_file"
      - "search"
    action: "allow"
    max_rate:
      count: 5
      window: 60

  - name: "deny-admin-tools"
    tools:
      - "delete_database"
    action: "deny"
    conditions:
      - field: "caller.trusted"
        operator: "eq"
        value: false

default_deny: false
```

## Filtering Tool List

```typescript
// Get list of allowed tools for a caller
const tools = mw.filterTools(callerCtx);
for (const tool of tools) {
  console.log(tool.name);
}
```

## Condition Operators

| Operator | Description |
|----------|-------------|
| `eq` | Field equals value |
| `not_eq` | Field does not equal value |
| `contains` | Field contains value |
| `not_contains` | Field does not contain value |
| `matches` | Field matches regex pattern |
| `not_matches` | Field does not match regex pattern |
| `exists` | Field exists |
| `not_exists` | Field does not exist |
| `not` | Field is empty |

## Field Resolution

Conditions can reference:
- `caller.role` - Caller's role
- `caller.userId` - User ID
- `caller.sessionId` - Session ID
- `caller.source` - Call source
- `caller.trusted` - Whether caller is trusted
- `args.<name>` - Tool argument values
- `context.<key>` - Custom context metadata

## API Reference

### Core Classes

- `Middleware` - Main middleware class for policy enforcement
- `Policy` - Policy container with rules
- `Rule` - Individual policy rule
- `CallerContext` - Context about the caller
- `ToolCall` - Represents a tool call request
- `ToolResult` - Represents a tool execution result

### Auditors

- `InMemoryAuditor` - Stores audit logs in memory
- `NoOpAuditor` - No-op auditor for performance

### Utilities

- `loadPolicyFromFile(path)` - Load policy from YAML file
- `loadPolicyFromYaml(yamlString)` - Load policy from YAML string
