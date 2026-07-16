import * as fs from "fs";
import * as path from "path";
import { EvalRunner } from "./runner.js";
import { FileSearchCases } from "./cases/file_search.js";
import { GeneralCases } from "./cases/general.js";

async function mockToolExecutor(toolName: string, args: Record<string, unknown>): Promise<string> {
  switch (toolName) {
    case "glob": {
      const pattern = (args.pattern as string) || "";
      const directory = (args.directory as string) || ".";
      const fullPattern = path.join(directory, pattern);
      const files = globSyncSimple(fullPattern).slice(0, 10);
      return JSON.stringify(files);
    }
    case "read_file": {
      const filePath = (args.path as string) || "";
      try {
        const content = fs.readFileSync(filePath, "utf-8");
        return content.slice(0, 1000);
      } catch {
        return `File not found: ${filePath}`;
      }
    }
    case "search_files":
      return JSON.stringify(["match in file1.go", "match in file2.go"]);
    case "calculator": {
      const expression = (args.expression as string) || "0";
      try {
        const result = safeEval(expression);
        return String(result);
      } catch (e) {
        return `Error: ${e}`;
      }
    }
    case "get_weather": {
      const location = (args.location as string) || "";
      return JSON.stringify({ location, temp: 72, condition: "sunny" });
    }
    case "translate": {
      const text = (args.text as string) || "";
      const targetLang = (args.target_lang as string) || "";
      return JSON.stringify({
        original: text,
        translated: `[translated: ${text}]`,
        target: targetLang,
      });
    }
    default:
      return `Mock result for ${toolName}`;
  }
}

function safeEval(expr: string): number {
  const sanitized = expr.replace(/[^0-9+\-*/().\s]/g, "");
  const result = Function(`"use strict"; return (${sanitized})`)();
  return Number(result);
}

function globSyncSimple(pattern: string): string[] {
  return [];
}

async function main() {
  const args = process.argv.slice(2);
  let fileSearch = false;
  let general = false;
  let models = "qwen3.6-27b-mtp";
  let baseURL = "http://pedrogpt:8000";
  let maxTurns = 10;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--file-search") fileSearch = true;
    else if (args[i] === "--general") general = true;
    else if (args[i] === "--models" && args[i + 1]) models = args[++i];
    else if (args[i] === "--base-url" && args[i + 1]) baseURL = args[++i];
    else if (args[i] === "--max-turns" && args[i + 1]) maxTurns = parseInt(args[++i], 10);
  }

  let cases;
  let outputFile: string;

  if (fileSearch) {
    cases = FileSearchCases;
    outputFile = "file_search_results.json";
  } else if (general) {
    cases = GeneralCases;
    outputFile = "general_results.json";
  } else {
    cases = [...FileSearchCases, ...GeneralCases];
    outputFile = "results.json";
  }

  const modelList = models.split(",").map((m) => m.trim()).filter(Boolean);

  const runner = new EvalRunner(baseURL, maxTurns);
  const report = await runner.runEvals(cases, modelList, mockToolExecutor);

  const outputDir = path.join("python", "src", "evals", "output");
  fs.mkdirSync(outputDir, { recursive: true });
  const outputPath = path.join(outputDir, outputFile);
  runner.saveReport(report, outputPath);

  console.log("\n=== Summary ===");
  for (const model of modelList) {
    const passRate = runner.passRate(model) * 100;
    console.log(`${model}: ${passRate.toFixed(1)}% pass rate`);
  }

  console.log(`\nResults saved to: ${outputPath}`);
}

main().catch(console.error);