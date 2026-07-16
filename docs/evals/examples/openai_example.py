"""
Example: Running evals with OpenAI API.

This example shows how to test your agent against OpenAI's API.
"""
import os
from evals.models import (
    ModelBackend,
    create_model_client,
    AgentExecutor,
)
from evals.runner import EvalRunner
from evals.cases.general import GeneralCases
from evals.cases.github import GITHUB_CASES


def create_tool_executor():
    """Create a tool executor that calls your actual tools."""
    def executor(tool_name: str, args: dict) -> str:
        # TODO: Replace with your actual tool implementations
        # This is where you'd call your backend services,
        # APIs, databases, etc.
        return f"Mock result for {tool_name}({args})"
    return executor


def run_openai_eval():
    """Run evals against OpenAI API."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    client = create_model_client(
        backend=ModelBackend.OPENAI,
        model="gpt-4o-mini",
        api_key=api_key,
    )

    tool_executor = create_tool_executor()
    agent = AgentExecutor(client, tool_executor, max_turns=10)
    runner = EvalRunner(base_url="https://api.openai.com/v1", max_turns=10)

    cases = GeneralCases + GITHUB_CASES
    models = ["gpt-4o-mini"]

    report = runner.run_evals(cases, models, tool_executor)

    print("\n=== Summary ===")
    for model in models:
        pass_rate = report.pass_rate(model) * 100
        print(f"{model}: {pass_rate:.1f}% pass rate")

    runner.save_report(report, "python/src/evals/output/openai_results.json")


if __name__ == "__main__":
    run_openai_eval()