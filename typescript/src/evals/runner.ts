import { ModelClient, ChatMessage, ToolDefinition } from "./models";

export { ToolDefinition };

export interface EvalCase {
  name: string;
  description: string;
  systemPrompt: string;
  userMessage: string;
  tools: ToolDefinition[];
  expectedTool: string;
  maxTurns: number;
}

export interface EvalResult {
  case_name: string;
  model_name: string;
  success: boolean;
  turns: number;
  tool_calls: Array<{ turn: number; name: string; arguments: string }>;
  error: string;
  duration_ms: number;
}

export interface EvalReport {
  timestamp: string;
  models: string[];
  results: EvalResult[];
}

export class EvalRunner {
  private baseURL: string;
  private maxTurns: number;
  private results: EvalResult[] = [];

  constructor(baseURL: string, maxTurns: number = 10) {
    this.baseURL = baseURL;
    this.maxTurns = maxTurns;
  }

  passRate(model: string): number {
    const modelResults = this.results.filter((r) => r.model_name === model);
    if (modelResults.length === 0) return 0.0;
    const passed = modelResults.filter((r) => r.success).length;
    return passed / modelResults.length;
  }

  async runCase(
    case_: EvalCase,
    model: string,
    toolExecutor: (toolName: string, args: Record<string, unknown>) => Promise<string>
  ): Promise<EvalResult> {
    const start = Date.now();
    const client = new ModelClient(this.baseURL, model);

    const messages: ChatMessage[] = [
      { role: "system", content: case_.systemPrompt },
      { role: "user", content: case_.userMessage },
    ];

    const toolCallsMade: Array<{ turn: number; name: string; arguments: string }> = [];
    let turns = 0;
    let error = "";

    try {
      while (turns < case_.maxTurns) {
        const result = await client.complete(messages, case_.tools, 0.0, 2048);
        turns++;

        if (result.tool_calls.length === 0) {
          break;
        }

        for (const tc of result.tool_calls) {
          toolCallsMade.push({
            turn: turns,
            name: tc.name,
            arguments: tc.arguments,
          });

          if (tc.name === case_.expectedTool) {
            const durationMs = Date.now() - start;
            return {
              case_name: case_.name,
              model_name: model,
              success: true,
              turns: turns,
              tool_calls: toolCallsMade,
              error: "",
              duration_ms: durationMs,
            };
          }

          const args = JSON.parse(tc.arguments);
          const toolResult = await toolExecutor(tc.name, args);

          messages.push({
            role: "assistant",
            content: "",
          });
          messages.push({
            role: "tool",
            content: toolResult,
          });
        }
      }

      const durationMs = Date.now() - start;
      error = `Expected tool '${case_.expectedTool}' not called in ${turns} turns`;
      return {
        case_name: case_.name,
        model_name: model,
        success: false,
        turns: turns,
        tool_calls: toolCallsMade,
        error: error,
        duration_ms: durationMs,
      };
    } catch (e) {
      const durationMs = Date.now() - start;
      return {
        case_name: case_.name,
        model_name: model,
        success: false,
        turns: turns,
        tool_calls: toolCallsMade,
        error: e instanceof Error ? e.message : String(e),
        duration_ms: durationMs,
      };
    }
  }

  async runEvals(
    cases: EvalCase[],
    models: string[],
    toolExecutor: (toolName: string, args: Record<string, unknown>) => Promise<string>
  ): Promise<EvalReport> {
    const report: EvalReport = {
      timestamp: new Date().toISOString(),
      models: models,
      results: [],
    };

    for (const model of models) {
      console.log(`\n=== Testing model: ${model} ===`);
      for (const case_ of cases) {
        process.stdout.write(`  Running: ${case_.name}...`);
        const result = await this.runCase(case_, model, toolExecutor);
        this.results.push(result);
        report.results.push(result);

        const status = result.success ? "PASS" : "FAIL";
        console.log(`${status} (${result.turns} turns, ${result.duration_ms}ms)`);

        if (!result.success) {
          console.log(`    Error: ${result.error}`);
        }
      }
    }

    return report;
  }

  saveReport(report: EvalReport, outputPath: string): void {
    const fs = require("fs");
    const dir = require("path").dirname(outputPath);
    fs.mkdirSync(dir, { recursive: true });

    const output = {
      timestamp: report.timestamp,
      models: report.models,
      results: report.results.map((r) => ({
        case: r.case_name,
        model: r.model_name,
        success: r.success,
        turns: r.turns,
        tool_calls: r.tool_calls,
        error: r.error,
        duration_ms: r.duration_ms,
      })),
    };

    fs.writeFileSync(outputPath, JSON.stringify(output, null, 2));
  }
}