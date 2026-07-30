/**
 * Wiki memory - TypeScript client for the Go core's ontology-constrained
 * wiki memory.
 *
 * WikiMemory spawns the Go MCP stdio server (`memctl serve`) scoped to one
 * user. The subprocess owns enforcement: every call passes the Go
 * middleware chain (declarative policy + ontology evaluator + audit), and
 * in-band attempts to change user scope are denied. The API is async
 * (subprocess I/O); inference stays in the Python SDK.
 */

import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { createInterface, type Interface } from "node:readline";

export const MEMORY_TOOLS = [
  "memory_ingest",
  "memory_write_page",
  "memory_query",
  "memory_get_claims",
  "memory_lint",
] as const;

export const DIAGNOSTICS_MARKER = "diagnostics: ";

/** Structured ontology violation from a DENY decision. */
export interface DiagnosticViolation {
  constraint: string;
  term: string;
  message: string;
  nearest: string[];
}

/** Extract structured violations from a deny reason, if present. */
export function parseDiagnostics(errorText: string): DiagnosticViolation[] {
  const idx = errorText.indexOf(DIAGNOSTICS_MARKER);
  if (idx < 0) return [];
  try {
    const raw = JSON.parse(errorText.slice(idx + DIAGNOSTICS_MARKER.length)) as Array<
      Record<string, unknown>
    >;
    return raw.map((v) => ({
      constraint: String(v.constraint ?? ""),
      term: String(v.term ?? ""),
      message: String(v.message ?? ""),
      nearest: Array.isArray(v.nearest) ? v.nearest.map(String) : [],
    }));
  } catch {
    return [];
  }
}

export class MemoryServerError extends Error {}

export interface WikiMemoryOptions {
  userId: string;
  root: string;
  tboxPaths: string[];
  /** Path to the memctl binary; defaults to $PEDRO_MEMCTL or "memctl". */
  memctlPath?: string;
  sessionId?: string;
}

/** Result triple matching the SDK's executor convention. */
export type ToolResult = [unknown, boolean, string];

interface RpcResponse {
  id?: number;
  result?: Record<string, unknown>;
  error?: { code: number; message: string };
}

export class WikiMemory {
  readonly userId: string;
  private proc: ChildProcessWithoutNullStreams;
  private lines: Interface;
  private pending: Array<{
    resolve: (r: Record<string, unknown>) => void;
    reject: (e: Error) => void;
  }> = [];
  private nextId = 0;
  private ready: Promise<void>;

  constructor(options: WikiMemoryOptions) {
    if (!options.userId) throw new MemoryServerError("userId is required");
    if (!options.tboxPaths.length) {
      throw new MemoryServerError("tboxPaths is required (the T-box is a parameter)");
    }
    const binary =
      options.memctlPath ?? process.env.PEDRO_MEMCTL ?? "memctl";
    const args = [
      "serve",
      "-root", options.root,
      "-user", options.userId,
      "-session", options.sessionId ?? "typescript-sdk",
    ];
    for (const path of options.tboxPaths) args.push("-tbox", path);
    this.userId = options.userId;
    this.proc = spawn(binary, args, { stdio: ["pipe", "pipe", "pipe"] });
    this.proc.on("error", (err) => this.failAll(new MemoryServerError(err.message)));
    this.proc.on("exit", (code) =>
      this.failAll(new MemoryServerError(`memory server exited (code=${code})`))
    );
    this.lines = createInterface({ input: this.proc.stdout });
    this.lines.on("line", (line) => this.onLine(line));
    this.ready = this.request("initialize", {}).then(() => {
      this.notify("notifications/initialized");
    });
  }

  private onLine(line: string): void {
    if (!line.trim()) return;
    const next = this.pending.shift();
    if (!next) return;
    let response: RpcResponse;
    try {
      response = JSON.parse(line) as RpcResponse;
    } catch (err) {
      next.reject(new MemoryServerError(`bad response: ${String(err)}`));
      return;
    }
    if (response.error) {
      next.reject(
        new MemoryServerError(`rpc ${response.error.code}: ${response.error.message}`)
      );
      return;
    }
    next.resolve(response.result ?? {});
  }

  private failAll(err: Error): void {
    const waiting = this.pending;
    this.pending = [];
    for (const p of waiting) p.reject(err);
  }

  private notify(method: string): void {
    this.proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", method }) + "\n");
  }

  private request(
    method: string,
    params: Record<string, unknown>
  ): Promise<Record<string, unknown>> {
    this.nextId += 1;
    const message = { jsonrpc: "2.0", id: this.nextId, method, params };
    return new Promise((resolve, reject) => {
      this.pending.push({ resolve, reject });
      this.proc.stdin.write(JSON.stringify(message) + "\n");
    });
  }

  /** Execute a memory tool. Resolves to [outputText, success, error]. */
  async execute(
    toolName: string,
    args: Record<string, unknown>
  ): Promise<ToolResult> {
    await this.ready;
    const result = await this.request("tools/call", {
      name: toolName,
      arguments: args,
    });
    const blocks = (result.content ?? []) as Array<{ type: string; text?: string }>;
    const text = blocks
      .filter((b) => b.type === "text")
      .map((b) => b.text ?? "")
      .join("");
    if (result.isError) return [null, false, text];
    return [text, true, ""];
  }

  /** List the memory tools served by the core. */
  async tools(): Promise<Array<{ name: string; description: string }>> {
    await this.ready;
    const result = await this.request("tools/list", {});
    return (result.tools ?? []) as Array<{ name: string; description: string }>;
  }

  async ingest(sourceId: string, text: string): Promise<ToolResult> {
    return this.execute("memory_ingest", { source_id: sourceId, text });
  }

  async writePage(content: string): Promise<ToolResult> {
    return this.execute("memory_write_page", { content });
  }

  async query(question: string): Promise<ToolResult> {
    return this.parsed(await this.execute("memory_query", { question }));
  }

  async getClaims(pageId?: string): Promise<ToolResult> {
    const args: Record<string, unknown> = {};
    if (pageId) args.page_id = pageId;
    return this.parsed(await this.execute("memory_get_claims", args));
  }

  async lint(): Promise<ToolResult> {
    return this.parsed(await this.execute("memory_lint", {}));
  }

  private parsed([output, ok, err]: ToolResult): ToolResult {
    if (!ok || typeof output !== "string" || output === "") return [output, ok, err];
    try {
      return [JSON.parse(output), ok, err];
    } catch {
      return [output, ok, err];
    }
  }

  /** Terminate the memory server subprocess. */
  close(): void {
    this.proc.stdin.end();
    this.proc.kill();
  }
}
