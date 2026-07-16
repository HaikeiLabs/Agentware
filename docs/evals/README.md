# Evals Package

A framework for evaluating LLM agents on tool-calling capabilities. Supports multiple model backends and runs evals against real models.

## Quick Start

```bash
# Python - run all evals against local llama.cpp
cd python
PYTHONPATH=src python3 -m evals.main --all --models qwen3.6-27b-mtp

# Go - run all evals
cd go && go run ./cmd/evals

# TypeScript - run all evals
cd typescript && node dist/evals/main.js
```

## CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `--file-search` | Run file search evals only | - |
| `--general` | Run general tool calling evals | - |
| `--github` | Run GitHub tool evals | - |
| `--calendar` | Run calendar tool evals | - |
| `--all` | Run all evals (default) | true |
| `--models` | Comma-separated model list | qwen3.6-27b-mtp |
| `--base-url` | API base URL | http://pedrogpt:8000 |
| `--backend` | Model backend (Python only) | llamacpp |
| `--max-turns` | Max turns per eval | 10 |

## Model Backends

### Python

```python
from evals.models import ModelBackend, create_model_client

client = create_model_client(
    backend=ModelBackend.LLAMACPP,
    model="qwen3.6-27b-mtp",
    base_url="http://pedrogpt:8000"
)
```

Supported backends:
- `ollama` - Local Ollama (http://localhost:11434)
- `llamacpp` - llama.cpp server (http://localhost:8000)
- `vllm` - vLLM server
- `lmstudio` - LM Studio
- `openai` - OpenAI API (requires OPENAI_API_KEY)
- `anthropic` - Anthropic API (requires ANTHROPIC_API_KEY)

### Go

```go
runner := evals.NewEvalRunner("http://pedrogpt:8000", 10)
```

### TypeScript

```typescript
const runner = new EvalRunner("http://pedrogpt:8000", 10);
```

## Test Cases

### File Search
- `glob_python_files` - Find Python files
- `glob_md_files` - Find Markdown files
- `search_code` - Search for code patterns
- `read_file` - Read configuration files

### General
- `calculator_add` - Simple addition
- `calculator_complex` - Complex expressions
- `get_weather` - Get weather info
- `translate_english_to_spanish` - Translation
- `translate_with_source` - Translation with source language

### GitHub
- `list_prs` - List pull requests
- `list_issues` - List issues
- `create_issue` - Create an issue
- `workflow_status` - Get workflow status

### Calendar
- `schedule_meeting` - Schedule a meeting
- `list_events` - List calendar events
- `find_free_time` - Find free time slots

## Adding New Test Cases

### Python

```python
from evals.runner import EvalCase

MY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "my_tool",
            "description": "Does something useful",
            "parameters": {
                "type": "object",
                "properties": {
                    "arg1": {"type": "string", "description": "First argument"}
                },
                "required": ["arg1"]
            }
        }
    }
]

MY_CASES = [
    EvalCase(
        name="my_tool_test",
        description="Test my tool",
        system_prompt="You are a helpful assistant with access to tools.",
        user_message="Use my_tool with arg1=value",
        tools=MY_TOOLS,
        expected_tool="my_tool",
        max_turns=10
    )
]
```

### Go

```go
var MyTools = []ToolDefinition{
    {
        Type: "function",
        Function: ToolFunc{
            Name:        "my_tool",
            Description: "Does something useful",
            Parameters: map[string]interface{}{...},
        },
    },
}

var MyCases = []EvalCase{
    {
        Name:         "my_tool_test",
        Description:  "Test my tool",
        SystemPrompt: "You are a helpful assistant with access to tools.",
        UserMessage:  "Use my_tool with arg1=value",
        Tools:        MyTools,
        ExpectedTool: "my_tool",
        MaxTurns:     10,
    },
}
```

### TypeScript

```typescript
const myTools: ToolDefinition[] = [
  {
    type: "function",
    function: {
      name: "my_tool",
      description: "Does something useful",
      parameters: { ... },
    },
  },
];

const myCases: EvalCase[] = [
  {
    name: "my_tool_test",
    description: "Test my tool",
    systemPrompt: "You are a helpful assistant with access to tools.",
    userMessage: "Use my_tool with arg1=value",
    tools: myTools,
    expectedTool: "my_tool",
    maxTurns: 10,
  },
];
```

## Custom Tool Executor

The tool executor function receives tool name and arguments, returns a string result:

```python
def tool_executor(tool_name: str, args: dict) -> str:
    if tool_name == "my_tool":
        # Call actual tool or return mock
        return '{"result": "success"}'
    return "Unknown tool"
```

## Agent Executor (Python)

For running agents that make multiple tool calls in a loop:

```python
from evals.models import AgentExecutor

agent = AgentExecutor(
    model_client=client,
    tool_executor=tool_executor,
    max_turns=10
)

result = agent.run(
    system_prompt="You are a helpful assistant.",
    user_message="Do something complex",
    tools=my_tools
)

print(result["tool_calls"])  # All tool calls made
print(result["turns"])       # Number of turns taken
print(result["success"])     # Whether any tool was called
```

## Output

Results are saved to `python/src/evals/output/results.json`:

```json
{
  "timestamp": "2024-01-15T10:00:00Z",
  "models": ["qwen3.6-27b-mtp"],
  "results": [
    {
      "case": "calculator_add",
      "model": "qwen3.6-27b-mtp",
      "success": true,
      "turns": 1,
      "tool_calls": [...],
      "duration_ms": 500
    }
  ]
}
```