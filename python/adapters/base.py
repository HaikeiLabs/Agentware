"""Base interfaces and types for agent adapters."""

from dataclasses import dataclass, field
from typing import Any, Protocol


class AgentBackend(Protocol):
    """Protocol for agent backends - matches Go ToolExecutor interface."""

    def execute(self, tool_name: str, args: dict[str, Any]) -> "AgentResult":
        """Execute a tool with the given name and arguments."""
        ...

    def list_tools(self) -> list["AgentTool"]:
        """List all available tools from this backend."""
        ...


@dataclass
class AgentTool:
    """Represents a tool exposed by an agent backend."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(self.name)


@dataclass
class AgentResult:
    """Result of a tool execution."""

    success: bool
    output: str | dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.success and self.error is None:
            raise ValueError("error must be set when success is False")
