import type { AnyTool } from "./tool.js";

export class ToolRegistry {
  private tools: Map<string, AnyTool> = new Map();

  register(tool: AnyTool): void {
    this.tools.set(tool.name, tool);
  }

  get(name: string): AnyTool | undefined {
    return this.tools.get(name);
  }

  all(): AnyTool[] {
    return Array.from(this.tools.values()).sort((a, b) =>
      a.name.localeCompare(b.name)
    );
  }

  names(): string[] {
    return Array.from(this.tools.keys()).sort();
  }

  schemas(): Record<string, Record<string, unknown>> {
    const schemas: Record<string, Record<string, unknown>> = {};
    for (const [name, tool] of this.tools) {
      if ("inputSchema" in tool) {
        schemas[name] = (tool as unknown as { inputSchema(): Record<string, unknown> }).inputSchema();
      }
    }
    return schemas;
  }

  clear(): void {
    this.tools.clear();
  }
}