"""Pedro Agentware - Agent middleware and tooling for LLM tool calling."""

__version__ = "0.1.0"

from .executor import Executor
from .jobs import Job, JobManager
from .llm import Backend, Message
from .llmcontext import ContextManager
from .middleware import Auditor, Middleware, PolicyEvaluator
from .prompts import PromptGenerator
from .reasoning import ReasoningAdapter
from .toolformat import ToolFormatter
from .tools import Result, Tool, ToolRegistry

__all__ = [
    "Tool",
    "ToolRegistry",
    "Result",
    "Middleware",
    "PolicyEvaluator",
    "Auditor",
    "Executor",
    "Job",
    "JobManager",
    "Message",
    "Backend",
    "ContextManager",
    "PromptGenerator",
    "ToolFormatter",
    "ReasoningAdapter",
]
