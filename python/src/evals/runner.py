"""
Eval harness runner - runs evals against models sequentially.
"""
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from evals.models import ModelBackend, create_model_client


class EndpointUnavailableError(RuntimeError):
    """Raised when the configured model endpoint cannot be reached.

    Surfaced instead of scoring every case as a failure, so a blocked model
    run is never mistaken for a completed one.
    """


@dataclass
class EvalCase:
    name: str
    description: str
    system_prompt: str
    user_message: str
    tools: list[dict[str, Any]]
    expected_tool: str
    max_turns: int = 10
    # Optional argument assertions, checked only when set. Existing suites
    # that assert tool selection alone keep their behaviour.
    expected_args: dict[str, Any] = field(default_factory=dict)
    """Arguments that must be present with exactly these values."""
    required_arg_keys: list[str] = field(default_factory=list)
    """Argument names that must be present, whatever their value."""
    forbidden_arg_keys: list[str] = field(default_factory=list)
    """Argument names that must NOT appear (e.g. proxy-delegated scoping)."""


def validate_tool_call(
    case: EvalCase, tool_name: str, raw_arguments: str
) -> tuple[bool, str]:
    """Check a tool call against the case's schema and argument assertions.

    Returns ``(ok, reason)``. Validates, in order: the tool name, that the
    arguments parse as a JSON object, that they satisfy the called tool's
    declared ``required`` schema fields and introduce no undeclared field,
    and finally the case's own expected/required/forbidden argument
    assertions.
    """
    if tool_name != case.expected_tool:
        return False, f"called {tool_name!r}, expected {case.expected_tool!r}"

    try:
        args = json.loads(raw_arguments) if raw_arguments else {}
    except json.JSONDecodeError as exc:
        return False, f"arguments are not valid JSON: {exc}"
    if not isinstance(args, dict):
        return False, f"arguments are not a JSON object: {type(args).__name__}"

    schema: dict[str, Any] = {}
    for tool in case.tools:
        fn = tool.get("function")
        if isinstance(fn, dict) and fn.get("name") == tool_name:
            params = fn.get("parameters")
            if isinstance(params, dict):
                schema = params
            break

    properties = schema.get("properties", {})
    if isinstance(properties, dict) and properties:
        undeclared = sorted(set(args) - set(properties))
        if undeclared:
            return False, f"arguments not declared in the tool schema: {undeclared}"

    required = schema.get("required", [])
    if isinstance(required, list):
        missing = sorted(k for k in required if k not in args)
        if missing:
            return False, f"missing schema-required arguments: {missing}"

    missing_keys = sorted(k for k in case.required_arg_keys if k not in args)
    if missing_keys:
        return False, f"missing expected arguments: {missing_keys}"

    present_forbidden = sorted(k for k in case.forbidden_arg_keys if k in args)
    if present_forbidden:
        return False, f"forbidden arguments present: {present_forbidden}"

    for key, want in case.expected_args.items():
        if key not in args:
            return False, f"expected argument {key!r} is absent"
        if args[key] != want:
            return False, f"argument {key!r} is {args[key]!r}, expected {want!r}"

    return True, ""


@dataclass
class EvalResult:
    case_name: str
    model_name: str
    success: bool
    turns: int
    tool_calls: list[dict[str, Any]]
    error: str = ""
    duration_ms: int = 0


@dataclass
class EvalReport:
    timestamp: str
    models: list[str]
    results: list[EvalResult] = field(default_factory=list)

    def pass_rate(self, model: str) -> float:
        model_results = [r for r in self.results if r.model_name == model]
        if not model_results:
            return 0.0
        passed = sum(1 for r in model_results if r.success)
        return passed / len(model_results)


class EvalRunner:
    def __init__(self, base_url: str, max_turns: int = 10, backend: ModelBackend = ModelBackend.OLLAMA):
        self.base_url = base_url
        self.max_turns = max_turns
        self.backend = backend
        self.results: list[EvalResult] = []

    def run_case(self, case: EvalCase, model: str,
                 tool_executor: Callable[[str, dict[str, Any]], str]) -> EvalResult:
        start = time.time()
        client = create_model_client(self.backend, model, self.base_url)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": case.system_prompt},
            {"role": "user", "content": case.user_message},
        ]

        tool_calls_made: list[dict[str, Any]] = []
        turns = 0

        try:
            while turns < case.max_turns:
                result = client.complete(messages, tools=case.tools)
                turns += 1

                if not result.tool_calls:
                    break

                for tc in result.tool_calls:
                    tool_calls_made.append({
                        "turn": turns,
                        "name": tc["name"],
                        "arguments": tc["arguments"]
                    })

                    if tc["name"] == case.expected_tool:
                        ok, reason = validate_tool_call(case, tc["name"], tc["arguments"])
                        duration_ms = int((time.time() - start) * 1000)
                        # The expected tool was reached, so the case is
                        # decided here either way: calling it with arguments
                        # that fail the schema is a failure, not a retry.
                        return EvalResult(
                            case_name=case.name,
                            model_name=model,
                            success=ok,
                            turns=turns,
                            tool_calls=tool_calls_made,
                            error="" if ok else f"invalid call to {tc['name']}: {reason}",
                            duration_ms=duration_ms
                        )

                    try:
                        parsed_args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    except json.JSONDecodeError:
                        parsed_args = {}
                    tool_result = tool_executor(tc["name"], parsed_args)
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc["arguments"]
                            }
                        }]
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_result
                    })

            duration_ms = int((time.time() - start) * 1000)
            return EvalResult(
                case_name=case.name,
                model_name=model,
                success=False,
                turns=turns,
                tool_calls=tool_calls_made,
                error=f"Expected tool '{case.expected_tool}' not called in {turns} turns",
                duration_ms=duration_ms
            )

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            return EvalResult(
                case_name=case.name,
                model_name=model,
                success=False,
                turns=turns,
                tool_calls=tool_calls_made,
                error=str(e),
                duration_ms=duration_ms
            )

    def preflight(self, model: str) -> None:
        """Raise ``EndpointUnavailableError`` if ``model`` cannot be reached.

        Without this, an unreachable endpoint turns every case into a FAIL,
        which is indistinguishable from a model that answered badly. A blocked
        model run must be reported as blocked, never as a 0% score.
        """
        client = create_model_client(self.backend, model, self.base_url)
        probe = [{"role": "user", "content": "ping"}]
        try:
            client.complete(probe, tools=None, temperature=0.0, max_tokens=1)
        except Exception as exc:
            raise EndpointUnavailableError(
                f"model {model!r} is not reachable at {self.base_url!r} "
                f"via the {self.backend.value} backend: {exc}"
            ) from exc

    def run_evals(self, cases: list[EvalCase], models: list[str],
                  tool_executor: Callable[[str, dict[str, Any]], str],
                  preflight: bool = True) -> EvalReport:
        report = EvalReport(
            timestamp=datetime.now().isoformat(),
            models=models
        )

        for model in models:
            print(f"\n=== Testing model: {model} ===")
            if preflight:
                self.preflight(model)
            for case in cases:
                print(f"  Running: {case.name}...", end=" ")
                result = self.run_case(case, model, tool_executor)
                self.results.append(result)
                report.results.append(result)

                status = "PASS" if result.success else "FAIL"
                print(f"{status} ({result.turns} turns, {result.duration_ms}ms)")

                if not result.success:
                    print(f"    Error: {result.error}")

        return report

    def save_report(self, report: EvalReport, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump({
                "timestamp": report.timestamp,
                "models": report.models,
                "results": [
                    {
                        "case": r.case_name,
                        "model": r.model_name,
                        "success": r.success,
                        "turns": r.turns,
                        "tool_calls": r.tool_calls,
                        "error": r.error,
                        "duration_ms": r.duration_ms
                    }
                    for r in report.results
                ]
            }, f, indent=2)
