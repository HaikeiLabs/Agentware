#!/usr/bin/env python3
"""
Main entry point for running evals.
Usage: python -m testing.evals.main [--file-search | --general | --all]
"""
import argparse
import glob
import json
import os
from pathlib import Path

from testing.evals.cases.file_search import FILE_SEARCH_CASES
from testing.evals.cases.general import GENERAL_CASES
from testing.evals.runner import EvalRunner


def get_cwd() -> Path:
    if hasattr(os, 'getcwd'):
        return Path(os.getcwd())
    return Path(".")


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
    
    return f"Mock result for {tool_name}"


def main():
    parser = argparse.ArgumentParser(description="Run evals against models")
    parser.add_argument("--file-search", action="store_true", help="Run file search evals only")
    parser.add_argument("--general", action="store_true", help="Run general tool calling evals only")
    parser.add_argument("--all", action="store_true", default=True, help="Run all evals (default)")
    parser.add_argument("--models", default="nemotron-3-super-120b", help="Comma-separated model list")
    parser.add_argument("--base-url", default="http://pedrogpt:8080/v1", help="API base URL")
    parser.add_argument("--max-turns", type=int, default=10, help="Max turns per eval")
    args = parser.parse_args()
    
    if args.file_search:
        cases = FILE_SEARCH_CASES
        output_file = "file_search_results.json"
    elif args.general:
        cases = GENERAL_CASES
        output_file = "general_results.json"
    else:
        cases = FILE_SEARCH_CASES + GENERAL_CASES
        output_file = "results.json"
    
    models = args.models.split(",")
    
    runner = EvalRunner(base_url=args.base_url, max_turns=args.max_turns)
    report = runner.run_evals(cases, models, mock_tool_executor)
    
    output_dir = Path("testing/evals/output")
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