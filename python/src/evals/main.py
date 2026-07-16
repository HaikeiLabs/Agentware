#!/usr/bin/env python3
"""
Main entry point for running evals.
Usage: python -m evals.main [--file-search | --general | --github | --calendar | --all]
"""
import argparse
import json
import os
from pathlib import Path

from evals.cases.file_search import FILE_SEARCH_CASES
from evals.cases.general import GENERAL_CASES
from evals.cases.github import GITHUB_CASES
from evals.cases.calendar import CALENDAR_CASES
from evals.models import ModelBackend
from evals.runner import EvalRunner


def mock_tool_executor(tool_name: str, args: dict) -> str:
    if tool_name == "glob":
        pattern = args.get("pattern", "")
        directory = args.get("directory", ".")
        files = list(Path(directory).glob(pattern))
        return json.dumps([str(f) for f in files[:10]])

    if tool_name == "read_file":
        path = args.get("path", "")
        try:
            with open(path, "r") as f:
                return f.read()[:1000]
        except FileNotFoundError:
            return f"File not found: {path}"

    if tool_name == "search_files":
        return json.dumps([f"match in {path}" for path in ["file1.go", "file2.go"]])

    if tool_name == "calculator":
        expr = args.get("expression", "0")
        try:
            result = eval(expr, {"__builtins__": {}}, {})
            return str(result)
        except Exception as e:
            return f"Error: {e}"

    if tool_name == "get_weather":
        return json.dumps({"location": args.get("location"), "temp": 72, "condition": "sunny"})

    if tool_name == "translate":
        return json.dumps({
            "original": args.get("text"),
            "translated": f"[translated: {args.get('text')}]",
            "target": args.get("target_lang")
        })

    if tool_name == "list_prs":
        return json.dumps([
            {"title": "Add feature", "number": 1, "state": "open"},
            {"title": "Fix bug", "number": 2, "state": "open"},
        ])

    if tool_name == "list_issues":
        return json.dumps([
            {"title": "Bug in login", "number": 1, "state": "open"},
        ])

    if tool_name == "create_issue":
        return json.dumps({
            "number": 3,
            "title": args.get("title"),
            "state": "open"
        })

    if tool_name == "get_workflow_status":
        return json.dumps({"status": "success", "conclusion": "passed"})

    if tool_name == "schedule_meeting":
        return json.dumps({
            "id": "meeting-123",
            "title": args.get("title"),
            "start_time": args.get("start_time"),
        })

    if tool_name == "list_events":
        return json.dumps([
            {"title": "Team standup", "start": "2024-01-15T09:00:00Z"}
        ])

    if tool_name == "find_free_time":
        return json.dumps([
            {"start": "2024-01-15T14:00:00Z", "end": "2024-01-15T14:30:00Z"}
        ])

    return f"Mock result for {tool_name}"


def main():
    parser = argparse.ArgumentParser(description="Run evals against models")
    parser.add_argument("--file-search", action="store_true", help="Run file search evals only")
    parser.add_argument("--general", action="store_true", help="Run general tool calling evals only")
    parser.add_argument("--github", action="store_true", help="Run GitHub tool evals only")
    parser.add_argument("--calendar", action="store_true", help="Run calendar tool evals only")
    parser.add_argument("--all", action="store_true", default=True, help="Run all evals (default)")
    parser.add_argument("--models", default="llama3.2", help="Comma-separated model list")
    parser.add_argument("--base-url", default="http://pedrogpt:8000", help="API base URL")
    parser.add_argument("--backend", default="llamacpp", choices=["openai", "anthropic", "ollama", "vllm", "lmstudio", "llamacpp"], help="Model backend")
    parser.add_argument("--max-turns", type=int, default=10, help="Max turns per eval")
    args = parser.parse_args()

    backend = ModelBackend(args.backend)

    if args.file_search:
        cases = FILE_SEARCH_CASES
        output_file = "file_search_results.json"
    elif args.general:
        cases = GENERAL_CASES
        output_file = "general_results.json"
    elif args.github:
        cases = GITHUB_CASES
        output_file = "github_results.json"
    elif args.calendar:
        cases = CALENDAR_CASES
        output_file = "calendar_results.json"
    else:
        cases = FILE_SEARCH_CASES + GENERAL_CASES + GITHUB_CASES + CALENDAR_CASES
        output_file = "results.json"

    models = [m.strip() for m in args.models.split(",") if m.strip()]

    runner = EvalRunner(base_url=args.base_url, max_turns=args.max_turns, backend=backend)
    report = runner.run_evals(cases, models, mock_tool_executor)

    output_dir = Path("python/src/evals/output")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_file
    runner.save_report(report, output_path)

    print("\n=== Summary ===")
    for model in models:
        pass_rate = report.pass_rate(model) * 100
        print(f"{model}: {pass_rate:.1f}% pass rate")

    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()