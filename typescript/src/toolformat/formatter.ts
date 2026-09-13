import type { AnyTool, Result } from "../tools/index.js";

export interface ParsedToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
  raw: string;
}

export interface ToolFormatter {
  formatToolDefinitions(tools: AnyTool[]): string;
  parseToolCalls(response: string): ParsedToolCall[];
  formatToolResult(name: string, result: Result): string;
  modelFamily(): string;
}

export class GenericFormatter implements ToolFormatter {
  formatToolDefinitions(tools: AnyTool[]): string {
    if (tools.length === 0) return "No tools available.";

    const lines = ["Available tools:"];
    for (const tool of tools) {
      lines.push(`- ${tool.name}: ${tool.description}`);
    }
    return lines.join("\n");
  }

  parseToolCalls(_response: string): ParsedToolCall[] {
    return [];
  }

  formatToolResult(name: string, result: Result): string {
    return result.success
      ? `Tool ${name} result: ${JSON.stringify(result.data)}`
      : `Tool ${name} error: ${result.error}`;
  }

  modelFamily(): string {
    return "generic";
  }
}