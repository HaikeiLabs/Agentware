"""Kitaru adapter for pedro-agentware."""

import os
from dataclasses import dataclass, field
from typing import Any

from ..base import AgentResult, AgentTool
from .client import Client


def get_default_base_url() -> str:
    """Get default Kitaru URL from environment or return localhost."""
    return os.environ.get("KITARU_URL", "http://localhost:8080")


@dataclass
class KitaruConfig:
    """Configuration for Kitaru adapter."""

    base_url: str = field(default_factory=get_default_base_url)
    api_key: str | None = None
    timeout: float = 60.0
    wait_interval: float = 2.0
    retry_count: int = 3


class KitaruAdapter:
    """Adapter for Kitaru flow execution engine.

    Maps tool names to Kitaru flow names and executes flows via REST API.
    """

    def __init__(
        self,
        client: Client,
        flow_mapping: dict[str, str],
        config: KitaruConfig | None = None,
    ):
        self._client = client
        self._flow_mapping = flow_mapping
        self._config = config or KitaruConfig()

    def execute(self, tool_name: str, args: dict[str, Any]) -> AgentResult:
        """Execute a tool by mapping to a Kitaru flow."""
        flow_name = self._flow_mapping.get(tool_name)
        if flow_name is None:
            return AgentResult(
                success=False,
                error=f"unknown tool: {tool_name}",
            )

        flow = self._client.flow(flow_name)
        try:
            execution = flow.run_with_wait(
                args,
                poll_interval=self._config.wait_interval,
            )
            return AgentResult(
                success=execution.status == "completed",
                output=str(execution.output) if execution.output else None,
                metadata={
                    "execution_id": execution.id,
                    "status": execution.status,
                    "tool_name": tool_name,
                    "flow_name": flow_name,
                },
            )
        except Exception as e:
            return AgentResult(
                success=False,
                error=f"flow execution failed: {e}",
                metadata={
                    "tool_name": tool_name,
                    "flow_name": flow_name,
                },
            )

    def list_tools(self) -> list[AgentTool]:
        """List all tools mapped to Kitaru flows."""
        tools = []
        for tool_name, flow_name in self._flow_mapping.items():
            tools.append(
                AgentTool(
                    name=tool_name,
                    description=f"Execute Kitaru flow: {flow_name}",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "inputs": {
                                "type": "object",
                                "description": "Flow input parameters",
                            },
                        },
                    },
                )
            )
        return tools


def create_adapter(
    base_url: str | None = None,
    api_key: str | None = None,
    flow_mapping: dict[str, str] | None = None,
    config: KitaruConfig | None = None,
) -> tuple[Client, KitaruAdapter]:
    """Create a Kitaru client and adapter.

    Args:
        base_url: Kitaru API base URL (defaults to KITARU_URL env or localhost:8080)
        api_key: Optional API key
        flow_mapping: Mapping of tool names to flow names
        config: Optional configuration

    Returns:
        Tuple of (Client, KitaruAdapter)
    """
    if base_url is None:
        base_url = get_default_base_url()
    client = Client(base_url=base_url, api_key=api_key)
    adapter = KitaruAdapter(
        client=client,
        flow_mapping=flow_mapping or {},
        config=config,
    )
    return client, adapter