"""
LLM provider abstraction.

SessionBuilderAgent (and any future agent) talks to this module instead
of a specific vendor SDK. Tool schemas are declared once in Anthropic's
`{name, description, input_schema}` shape (the canonical format used
throughout this codebase); each provider converts that to its own wire
format internally.

Switch providers with the LLM_PROVIDER env var: "anthropic" | "openai" |
"deepseek". DeepSeek's API is OpenAI-compatible, so it reuses
OpenAICompatibleProvider with a different base_url/model/api key.
"""

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class ToolResult:
    id: str
    name: str
    output: dict


@dataclass
class LLMTurn:
    text: str
    tool_calls: List[ToolCall] = field(default_factory=list)

    @property
    def is_final(self) -> bool:
        return len(self.tool_calls) == 0


class LLMProvider(ABC):
    @abstractmethod
    def start_conversation(self, system: str, user_message: str) -> None:
        ...

    @abstractmethod
    def step(self, tools: List[dict]) -> LLMTurn:
        ...

    @abstractmethod
    def submit_tool_results(self, results: List[ToolResult]) -> None:
        ...


class AnthropicProvider(LLMProvider):
    def __init__(self, model: str, api_key: Optional[str] = None):
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)
        self._model = model
        self._system = ""
        self._messages: list = []

    def start_conversation(self, system: str, user_message: str) -> None:
        self._system = system
        self._messages = [{"role": "user", "content": user_message}]

    def step(self, tools: List[dict]) -> LLMTurn:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            system=self._system,
            tools=tools,
            messages=self._messages,
        )
        self._messages.append({"role": "assistant", "content": response.content})

        text = "".join(
            block.text.strip() for block in response.content if block.type == "text"
        )
        tool_calls = [
            ToolCall(id=block.id, name=block.name, input=block.input)
            for block in response.content
            if block.type == "tool_use"
        ]
        return LLMTurn(text=text, tool_calls=tool_calls)

    def submit_tool_results(self, results: List[ToolResult]) -> None:
        self._messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r.id,
                        "content": json.dumps(r.output),
                    }
                    for r in results
                ],
            }
        )


def _to_openai_tools(tools: List[dict]) -> List[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


class OpenAICompatibleProvider(LLMProvider):
    """Works for OpenAI itself and any OpenAI-compatible API (DeepSeek)."""

    def __init__(self, model: str, api_key: Optional[str] = None, base_url: Optional[str] = None):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._messages: list = []

    def start_conversation(self, system: str, user_message: str) -> None:
        self._messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ]

    def step(self, tools: List[dict]) -> LLMTurn:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=self._messages,
            tools=_to_openai_tools(tools),
        )
        message = response.choices[0].message
        self._messages.append(message.model_dump(exclude_none=True))

        tool_calls = [
            ToolCall(
                id=tc.id,
                name=tc.function.name,
                input=json.loads(tc.function.arguments or "{}"),
            )
            for tc in (message.tool_calls or [])
        ]
        return LLMTurn(text=message.content or "", tool_calls=tool_calls)

    def submit_tool_results(self, results: List[ToolResult]) -> None:
        for r in results:
            self._messages.append(
                {
                    "role": "tool",
                    "tool_call_id": r.id,
                    "content": json.dumps(r.output),
                }
            )


_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
}


def get_llm_provider() -> LLMProvider:
    """
    Reads LLM_PROVIDER (default "deepseek") and optional LLM_MODEL from
    the environment and returns a ready-to-use provider. Each provider
    reads its own API key from the conventional env var for that vendor
    (ANTHROPIC_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY).
    """
    provider_name = os.getenv("LLM_PROVIDER", "deepseek").lower()
    model = os.getenv("LLM_MODEL") or _DEFAULT_MODELS.get(provider_name)

    if provider_name == "anthropic":
        return AnthropicProvider(model=model, api_key=os.getenv("ANTHROPIC_API_KEY"))
    elif provider_name == "openai":
        return OpenAICompatibleProvider(model=model, api_key=os.getenv("OPENAI_API_KEY"))
    elif provider_name == "deepseek":
        return OpenAICompatibleProvider(
            model=model,
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider_name!r}")
