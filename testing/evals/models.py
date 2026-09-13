"""
Model client for OpenAI-compatible API.
"""
import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Any


@dataclass
class ModelResult:
    content: str
    tool_calls: list[dict[str, Any]]
    finish_reason: str
    usage: dict[str, int]


class ModelClient:
    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: int = 60):
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, messages: list[dict], tools: list[dict] = None, 
                 temperature: float = 0.0, max_tokens: int = 2048) -> ModelResult:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if tools:
            payload["tools"] = tools
        
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8')}")
        
        choice = data["choices"][0]
        
        tool_calls = []
        if choice["message"].get("tool_calls"):
            for tc in choice["message"]["tool_calls"]:
                tool_calls.append({
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"]
                })
        
        return ModelResult(
            content=choice["message"].get("content", ""),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", ""),
            usage=data.get("usage", {})
        )