"""Pydantic AI adapter for pedro-agentware."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..base import AgentResult, AgentTool

if TYPE_CHECKING:
    from pydantic_ai import Agent
else:
    Agent = None


@dataclass
class PydanticConfig:
    """Configuration for Pydantic adapter."""

    timeout: float = 60.0
    max_retries: int = 3


class PydanticAdapter:
    """Adapter for Pydantic AI agents.

    Wraps a Pydantic AI agent to expose its tools as AgentBackend.
    """

    def __init__(
        self,
        agent: "Agent[Any, Any]",
        config: PydanticConfig | None = None,
    ):
        if Agent is None:
            raise ImportError("pydantic-ai is not installed. Install with: pip install pydantic-ai")
        self._agent = agent
        self._config = config or PydanticConfig()
        self._tools_cache: list[AgentTool] | None = None

    def execute(self, tool_name: str, args: dict[str, Any]) -> AgentResult:
        """Execute a tool by running the Pydantic AI agent.

        Note: Pydantic AI agents run as a full agent loop. This implementation
        simplifies by treating tool execution as agent runs with explicit context.
        For more granular control, consider using the tool definitions directly.
        """
        import asyncio
        from concurrent.futures import TimeoutError as ConTimeoutError

        if TYPE_CHECKING:
            import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return AgentResult(
                    success=False,
                    error="Cannot execute sync in async context. Use PydanticAdapterAsync.",
                )
        except RuntimeError:
            loop = None

        try:
            if loop:
                future = loop.run_in_executor(
                    None,
                    self._execute_sync,
                    tool_name,
                    args,
                )
                result = loop.run_until_complete(
                    asyncio.wait_for(future, timeout=self._config.timeout)
                )
            else:
                result = asyncio.run(self._execute_async(tool_name, args))
            return result
        except ConTimeoutError:
            return AgentResult(
                success=False,
                error=f"timeout after {self._config.timeout}s",
                metadata={"tool_name": tool_name},
            )
        except Exception as e:
            return AgentResult(
                success=False,
                error=str(e),
                metadata={"tool_name": tool_name},
            )

    def _execute_sync(self, tool_name: str, args: dict[str, Any]) -> AgentResult:
        """Synchronous execution."""
        import asyncio as asyncio_lib
        return asyncio_lib.run(self._execute_async(tool_name, args))

    async def _execute_async(self, tool_name: str, args: dict[str, Any]) -> AgentResult:
        """Async execution."""
        try:
            # Run the agent with explicit tool context
            result = await self._agent.run(
                f"Please execute the tool '{tool_name}' with the following parameters: {args}",
                timeout=self._config.timeout,
            )
            return AgentResult(
                success=True,
                output=str(result.data),
                metadata={
                    "tool_name": tool_name,
                    "model": result.model,
                },
            )
        except Exception as e:
            return AgentResult(
                success=False,
                error=str(e),
                metadata={"tool_name": tool_name},
            )

    def list_tools(self) -> list[AgentTool]:
        """List all tools from the Pydantic AI agent."""
        if self._tools_cache is not None:
            return self._tools_cache

        try:
            from pydantic_ai.tools import ToolDefinition

            tools: list[AgentTool] = []
            for tool in self._agent._tools:  # type: ignore[attr-defined]
                if isinstance(tool, ToolDefinition):
                    tools.append(
                        AgentTool(
                            name=tool.name,
                            description=tool.description,
                            input_schema=tool.parameters_json_schema or {},
                        )
                    )
            self._tools_cache = tools
            return self._tools_cache
        except Exception:
            return []

    def refresh_tools(self) -> None:
        """Refresh the tools cache."""
        self._tools_cache = None


class PydanticAdapterAsync:
    """Async version of Pydantic adapter for use in async contexts."""

    def __init__(
        self,
        agent: "Agent[Any, Any]",
        config: PydanticConfig | None = None,
    ):
        self._agent = agent
        self._config = config or PydanticConfig()

    async def execute(self, tool_name: str, args: dict[str, Any]) -> AgentResult:
        """Execute tool asynchronously."""
        try:
            result = await self._agent.run(
                f"Please execute the tool '{tool_name}' with the following parameters: {args}",
                timeout=self._config.timeout,
            )
            return AgentResult(
                success=True,
                output=str(result.data),
                metadata={
                    "tool_name": tool_name,
                    "model": result.model,
                },
            )
        except Exception as e:
            return AgentResult(
                success=False,
                error=str(e),
                metadata={"tool_name": tool_name},
            )

    def list_tools(self) -> list[AgentTool]:
        """List all tools from the Pydantic AI agent."""
        return []


def create_adapter(
    agent: "Agent[Any, Any]",
    timeout: float = 60.0,
    max_retries: int = 3,
) -> PydanticAdapter:
    """Create a Pydantic adapter from an existing agent.

    Args:
        agent: Pydantic AI agent instance
        timeout: Execution timeout in seconds
        max_retries: Maximum retry attempts

    Returns:
        PydanticAdapter instance
    """
    config = PydanticConfig(timeout=timeout, max_retries=max_retries)
    return PydanticAdapter(agent=agent, config=config)