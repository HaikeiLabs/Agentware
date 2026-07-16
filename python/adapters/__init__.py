"""Python agent adapters for pedro-agentware.

Provides adapters for connecting to various agent backends:
- Kitaru: Durable execution runtime
- Hermes: Self-improving agent from Nous Research
- Pydantic: Type-safe agents with PydanticAI
"""

from .base import AgentBackend, AgentResult, AgentTool

__all__ = [
    "AgentBackend",
    "AgentResult",
    "AgentTool",
]
