/**
 * Framework integration: expose wiki-memory tools in the Vercel AI SDK's
 * tool shape ({ description, parameters, execute }).
 *
 * The returned record plugs directly into `generateText`/`streamText`:
 *
 *   const memory = new WikiMemory({ userId: "alice", root, tboxPaths });
 *   const result = await generateText({ model, tools: memoryTools(memory), ... });
 *
 * Parameters are zod schemas (zod is already an SDK dependency). Denied
 * writes resolve to "DENIED: ..." including the structured diagnostics
 * payload, so the calling agent can self-correct and retry.
 */

import { z } from "zod";

import type { ToolResult, WikiMemory } from "./client.js";

export interface MemoryTool {
  description: string;
  parameters: z.ZodTypeAny;
  execute: (args: Record<string, unknown>) => Promise<string>;
}

function render([output, ok, err]: ToolResult): string {
  if (!ok) return `DENIED: ${err}`;
  if (typeof output === "string") return output;
  return JSON.stringify(output, null, 2);
}

export function memoryTools(memory: WikiMemory): Record<string, MemoryTool> {
  return {
    memory_ingest: {
      description: "Store a raw source document in the user's memory vault.",
      parameters: z.object({
        source_id: z.string().describe("kebab-case source id, e.g. src-go-blog"),
        text: z.string().describe("verbatim source text"),
      }),
      execute: async (args) =>
        render(await memory.ingest(String(args.source_id), String(args.text))),
    },
    memory_write_page: {
      description:
        "Create or update an ontology-validated wiki page. content is full " +
        "page markdown with YAML frontmatter per the memory schema; on DENY " +
        "the response includes structured diagnostics - fix and retry.",
      parameters: z.object({
        content: z.string().describe("full page markdown including frontmatter"),
      }),
      execute: async (args) => render(await memory.writePage(String(args.content))),
    },
    memory_query: {
      description: "Query the user's wiki memory.",
      parameters: z.object({ question: z.string() }),
      execute: async (args) => render(await memory.query(String(args.question))),
    },
    memory_get_claims: {
      description: "List claims tracked in the user's vault, optionally per page.",
      parameters: z.object({ page_id: z.string().optional() }),
      execute: async (args) =>
        render(
          await memory.getClaims(args.page_id ? String(args.page_id) : undefined)
        ),
    },
    memory_lint: {
      description: "Report contract, ontology, and graph issues in the vault.",
      parameters: z.object({}),
      execute: async () => render(await memory.lint()),
    },
  };
}
