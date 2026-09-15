#!/usr/bin/env python3
"""
Main entry point for running evals.
Usage: python -m evals.main [--file-search | --general | --github | --calendar
                            | --beta-tools | --all]
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from evals.cases.beta_tools import BETA_TOOL_CASES, BETA_TOOLS
from evals.cases.calendar import CALENDAR_CASES
from evals.cases.file_search import FILE_SEARCH_CASES
from evals.cases.general import GENERAL_CASES
from evals.cases.github import GITHUB_CASES
from evals.models import ModelBackend
from evals.runner import EndpointUnavailableError, EvalRunner


def beta_tool_executor(tool_name: str, args: dict[str, Any]) -> str:
    """Mock executor for the beta tool surface.

    Returns connector-shaped results, and the downstream failures and policy
    denials the beta cases probe. Denial strings here are *simulated* model
    inputs so we can observe recovery behaviour -- real enforcement lives in
    the middleware policy layer and is pinned by
    ``tests/beta_tool_authorization_test.py``.

    Delegated context (tenant, repository, bucket, workspace, drive) is never
    read from ``args``: the tenant-side proxy supplies it, so this mock
    reports it as proxy-supplied rather than echoing agent input.
    """
    proxy_scope = {"tenant_id": "<proxy-supplied>", "delegated": True}

    if tool_name == "github.get_issue":
        number = args.get("issue_number")
        if str(number) == "429":
            return json.dumps(
                {"error": "rate_limited", "retry_after_seconds": 30, "source": "provider"}
            )
        return json.dumps(
            {
                "issue_number": number,
                "title": "Login times out on retry",
                "state": "open",
                "scope": proxy_scope,
            }
        )

    if tool_name == "github.get_pull_request":
        return json.dumps(
            {
                "pr_number": args.get("pr_number"),
                "title": "Fix login timeout",
                "state": "open",
                "scope": proxy_scope,
            }
        )

    if tool_name == "linear.list_issues":
        return json.dumps(
            {
                "issues": [{"key": "ENG-201", "state": "in_progress"}],
                "scope": proxy_scope,
            }
        )

    if tool_name == "drive.list_files":
        return json.dumps(
            {
                "files": [{"id": "1a2b3c", "name": "Q3 revenue", "mime_type": "spreadsheet"}],
                "scope": proxy_scope,
            }
        )

    if tool_name == "docs.get_document":
        if args.get("document_id") == "denied-doc":
            return json.dumps(
                {
                    "error": "denied",
                    "reason": "resource outside the caller's granted scope",
                    "source": "policy",
                }
            )
        return json.dumps(
            {"document_id": args.get("document_id"), "text": "...", "scope": proxy_scope}
        )

    if tool_name == "s3.list_objects":
        prefix = str(args.get("prefix", ""))
        if prefix.startswith("unavailable/"):
            return json.dumps(
                {"error": "connector_unavailable", "source": "connector", "retryable": True}
            )
        return json.dumps(
            {"objects": [{"key": f"{prefix}app.log", "size": 1024}], "scope": proxy_scope}
        )

    if tool_name == "http_api.get_record":
        if str(args.get("record_id", "")).startswith("missing-"):
            return json.dumps({"error": "not_found", "source": "provider"})
        return json.dumps(
            {
                "entity": args.get("entity"),
                "record_id": args.get("record_id"),
                "scope": proxy_scope,
            }
        )

    if tool_name == "create_issue":
        if "denied-by-policy" in str(args.get("title", "")):
            return json.dumps(
                {
                    "error": "denied",
                    "reason": "missing required permission: github_write",
                    "source": "policy",
                }
            )
        return json.dumps({"number": 3, "title": args.get("title"), "state": "open"})

    if tool_name == "create_pull_request":
        return json.dumps(
            {
                "number": 9,
                "title": args.get("title"),
                "head": args.get("head"),
                "base": args.get("base", "main"),
            }
        )

    if tool_name == "crm_create_lead":
        email = str(args.get("email", ""))
        if "@" not in email:
            return json.dumps(
                {"error": "invalid_argument", "field": "email", "source": "validation"}
            )
        return json.dumps({"lead_id": "lead-77", "email": email})

    if tool_name == "schedule_meeting":
        return json.dumps(
            {
                "id": "meeting-123",
                "title": args.get("title"),
                "start_time": args.get("start_time"),
            }
        )

    if tool_name == "search_wiki":
        return json.dumps({"results": [{"title": "Proxy boundary decision", "score": 0.91}]})

    if tool_name == "web_search":
        return json.dumps({"results": [{"title": "Result", "url": "https://example.com"}]})

    return f"Mock result for {tool_name}"


def mock_tool_executor(tool_name: str, args: dict[str, Any]) -> str:
    if tool_name == "glob":
        pattern = args.get("pattern", "")
        directory = args.get("directory", ".")
        files = list(Path(directory).glob(pattern))
        return json.dumps([str(f) for f in files[:10]])

    if tool_name == "read_file":
        path = args.get("path", "")
        try:
            with open(path) as f:
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


def _beta_tool_names() -> frozenset[str]:
    names: set[str] = set()
    for tool in BETA_TOOLS:
        fn = tool.get("function")
        if isinstance(fn, dict):
            name = fn.get("name")
            if isinstance(name, str):
                names.add(name)
    return frozenset(names)


_BETA_TOOL_NAMES = _beta_tool_names()


def dispatch_tool_executor(tool_name: str, args: dict[str, Any]) -> str:
    """Route a tool call to the beta or the legacy mock executor.

    Beta names win so a combined run exercises the beta connector/failure
    behaviour, while shared names outside the beta surface keep their existing
    mock results.
    """
    if tool_name in _BETA_TOOL_NAMES:
        return beta_tool_executor(tool_name, args)
    return mock_tool_executor(tool_name, args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run evals against models")
    parser.add_argument("--file-search", action="store_true", help="Run file search evals only")
    parser.add_argument("--general", action="store_true", help="Run general tool calling evals only")
    parser.add_argument("--github", action="store_true", help="Run GitHub tool evals only")
    parser.add_argument("--calendar", action="store_true", help="Run calendar tool evals only")
    parser.add_argument(
        "--beta-tools", action="store_true", help="Run beta tool surface evals only"
    )
    parser.add_argument("--all", action="store_true", default=True, help="Run all evals (default)")
    parser.add_argument(
        "--models",
        default=os.environ.get("EVAL_MODELS", "llama3.2"),
        help="Comma-separated model list (default: $EVAL_MODELS)",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("EVAL_BASE_URL", "http://pedrogpt:8000"),
        help="API base URL (default: $EVAL_BASE_URL)",
    )
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
    elif args.beta_tools:
        cases = BETA_TOOL_CASES
        output_file = "beta_tools_results.json"
    else:
        cases = (
            FILE_SEARCH_CASES + GENERAL_CASES + GITHUB_CASES + CALENDAR_CASES + BETA_TOOL_CASES
        )
        output_file = "results.json"

    models = [m.strip() for m in args.models.split(",") if m.strip()]

    runner = EvalRunner(base_url=args.base_url, max_turns=args.max_turns, backend=backend)
    try:
        report = runner.run_evals(cases, models, dispatch_tool_executor)
    except EndpointUnavailableError as exc:
        # A blocked model run is reported as blocked and exits non-zero. It is
        # never written out as a 0% score, which would read as "the model
        # failed every case".
        print(f"\nBLOCKED: model run did not execute.\n  {exc}", file=sys.stderr)
        print(
            "  Set EVAL_BASE_URL (or --base-url) and --backend to a reachable "
            "OpenAI-compatible endpoint, then re-run.",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc

    # Anchored to this module, not the CWD, so results land in the same
    # directory whether the runner is invoked from the repo root or python/.
    output_dir = Path(__file__).resolve().parent / "output"
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
