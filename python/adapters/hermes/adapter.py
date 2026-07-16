"""Hermes adapter for pedro-agentware."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..base import AgentResult, AgentTool
from .client import Client


@dataclass
class HermesConfig:
    """Configuration for Hermes adapter."""

    config_path: Path | None = None
    hermes_path: str = "hermes"
    timeout: float = 60.0


class HermesAdapter:
    """Adapter for Hermes Agent.

    Wraps the Hermes CLI to expose tools as AgentBackend.
    """

    def __init__(
        self,
        client: Client,
        config: HermesConfig | None = None,
    ):
        self._client = client
        self._config = config or HermesConfig()
        self._tool_cache: list[AgentTool] | None = None

    def execute(self, tool_name: str, args: dict[str, Any]) -> AgentResult:
        """Execute a tool via Hermes."""
        output, error = self._client.execute(
            tool_name,
            args,
            timeout=self._config.timeout,
        )
        if error:
            return AgentResult(
                success=False,
                error=error,
                metadata={"tool_name": tool_name},
            )
        return AgentResult(
            success=True,
            output=output,
            metadata={"tool_name": tool_name},
        )

    def list_tools(self) -> list[AgentTool]:
        """List all available tools from Hermes."""
        if self._tool_cache is not None:
            return self._tool_cache

        hermes_tools = self._client.list_tools()
        self._tool_cache = [
            AgentTool(
                name=t.name,
                description=t.description,
            )
            for t in hermes_tools
        ]
        return self._tool_cache

    def refresh_tools(self) -> None:
        """Refresh the tool cache."""
        self._tool_cache = None


def create_adapter(
    config_path: Path | None = None,
    hermes_path: str = "hermes",
    timeout: float = 60.0,
) -> tuple[Client, HermesAdapter]:
    """Create a Hermes client and adapter.

    Args:
        config_path: Path to Hermes config directory
        hermes_path: Path to hermes CLI
        timeout: Execution timeout in seconds

    Returns:
        Tuple of (Client, HermesAdapter)
    """
    client = Client(config_path=config_path, hermes_path=hermes_path)
    config = HermesConfig(
        config_path=config_path,
        hermes_path=hermes_path,
        timeout=timeout,
    )
    adapter = HermesAdapter(client=client, config=config)
    return client, adapter