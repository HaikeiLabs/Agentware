"""
Eval harness runner - runs evals against models sequentially.
"""
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from testing.evals.models import ModelClient


@dataclass
class EvalCase:
    name: str
    description: str
    system_prompt: str
    user_message: str
    tools: list[dict]
    expected_tool: str
    max_turns: int = 10


@dataclass
class EvalResult:
    case_name: str
    model_name: str
    success: bool
    turns: int
    tool_calls: list[dict]
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
    def __init__(self, base_url: str, max_turns: int = 10):
        self.base_url = base_url
        self.max_turns = max_turns
        self.results: list[EvalResult] = []

    def run_case(self, case: EvalCase, model: str, 
                 tool_executor: Callable[[str, dict], str]) -> EvalResult:
        start = time.time()
        client = ModelClient(self.base_url, model)
        
        messages = [
            {"role": "system", "content": case.system_prompt},
            {"role": "user", "content": case.user_message},
        ]
        
        tool_calls_made = []
        turns = 0
        error = ""
        
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
                        duration_ms = int((time.time() - start) * 1000)
                        return EvalResult(
                            case_name=case.name,
                            model_name=model,
                            success=True,
                            turns=turns,
                            tool_calls=tool_calls_made,
                            duration_ms=duration_ms
                        )
                    
                    tool_result = tool_executor(tc["name"], json.loads(tc["arguments"]))
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

    def run_evals(self, cases: list[EvalCase], models: list[str],
                  tool_executor: Callable[[str, dict], str]) -> EvalReport:
        report = EvalReport(
            timestamp=datetime.now().isoformat(),
            models=models
        )
        
        for model in models:
            print(f"\n=== Testing model: {model} ===")
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

    def save_report(self, report: EvalReport, output_path: Path):
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