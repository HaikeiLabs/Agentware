# @pedro/agentware

`@pedro/agentware` provides tool and agent-runtime primitives for applications
that already own their agent loop, channel integration, identities, and tool
handlers.

## Async tool wrapper

Use `wrapTool` to make an existing tool callable through a consistent async
boundary. It preserves the host's input, output, and trusted context types;
Agentware does not infer identity or privileges from tool arguments.

```ts
import { wrapTool } from "@pedro/agentware";

type Selection = { queryId: string };
type TrustedContext = { principalId: string; verifiedGrant: string };

const queryModel = wrapTool(
  async (selection: Selection, context: TrustedContext, signal: AbortSignal) => {
    // Keep the application's existing authorization and provider guard here.
    return runExistingTool(selection, context.verifiedGrant, signal);
  },
  { name: "semantic-model-query", timeoutMs: 5_000 },
);

const result = await queryModel(
  { queryId: "commission-summary" },
  trustedContext,
  { signal: request.signal },
);
```

The wrapper propagates host cancellation and deadlines to the handler's
`AbortSignal`. It raises `ToolAbortedError` when the host cancels and
`ToolTimeoutError` when its configured deadline expires. Lifecycle hooks expose
only tool name, outcome, and duration; they intentionally exclude raw inputs
and host context.

## Integration boundary

Register only the wrapped handler with an agent framework or tool registry.
Keep channel ingress, identity verification, delegated credentials, and
domain-specific authorization in the host application. Agentware is not a
policy engine; a policy gate can wrap this same boundary later.
