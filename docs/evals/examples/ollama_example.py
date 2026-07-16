"""
Example: Running evals with Ollama locally.

This example shows how to test your agent against a local Ollama model.
Run this script to evaluate your agent's tool-calling ability.
"""
from evals.models import (
    ModelBackend,
    create_model_client,
    AgentExecutor,
)
from evals.runner import EvalRunner, EvalCase
from evals.cases.general import GENERAL_TOOLS, GeneralCases
from evals.cases.github import GITHUB_TOOLS, GITHUB_CASES


def create_tool_executor():
    """
    Create a real tool executor that calls actual tools.
    Replace this with your actual tool execution logic.
    """
    def executor(tool_name: str, args: dict) -> str:
        if tool_name == "calculator":
            expr = args.get("expression", "0")
            try:
                result = eval(expr, {"__builtins__": {}}, {})
                return str(result)
            except Exception as e:
                return f"Error: {e}"

        elif tool_name == "get_weather":
            import json
            return json.dumps({
                "location": args.get("location"),
                "temp": 72,
                "condition": "sunny"
            })

        elif tool_name == "list_prs":
            import json
            return json.dumps([
                {"title": "Add new feature", "number": 42, "state": "open"},
                {"title": "Fix bug", "number": 41, "state": "open"},
            ])

        elif tool_name == "list_issues":
            import json
            return json.dumps([
                {"title": "Login broken", "number": 10, "state": "open"},
            ])

        # Add more tool implementations as needed
        return f"Mock result for {tool_name}"

    return executor


def run_ollama_eval():
    """Run evals against local Ollama model."""
    # Create model client for Ollama
    client = create_model_client(
        backend=ModelBackend.OLLAMA,
        model="llama3.2",  # or your preferred model
        base_url="http://localhost:11434",
    )

    # Create tool executor
    tool_executor = create_tool_executor()

    # Create agent executor
    agent = AgentExecutor(
        model_client=client,
        tool_executor=tool_executor,
        max_turns=10,
    )

    # Create runner
    runner = EvalRunner(base_url="http://localhost:11434", max_turns=10)

    # Run evals
    cases = GeneralCases + GITHUB_CASES
    models = ["llama3.2"]

    report = runner.run_evals(cases, models, tool_executor)

    # Print summary
    print("\n=== Summary ===")
    for model in models:
        pass_rate = report.pass_rate(model) * 100
        print(f"{model}: {pass_rate:.1f}% pass rate")

    # Save results
    runner.save_report(report, "python/src/evals/output/ollama_results.json")
    print(f"\nResults saved to: python/src/evals/output/ollama_results.json")


if __name__ == "__main__":
    run_ollama_eval()