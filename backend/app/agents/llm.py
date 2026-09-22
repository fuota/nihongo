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

For image-input calls (kanji recognition), use get_vision_llm_provider()
instead -- it reads a separate VISION_LLM_PROVIDER env var (default
"anthropic"), since DeepSeek has no vision input and shouldn't silently
become the vision provider just because it's the default chat one.
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

    def recognize_image(self, image_base64: str, prompt: str) -> str:
        """
        One-shot vision query: send a single image + text prompt, get back
        the model's raw text response. Independent of the tool-use
        conversation state above. Not all providers support this (e.g.
        DeepSeek's chat API has no vision input) -- use get_vision_llm_provider()
        to get one that does, rather than calling this on whatever
        get_llm_provider() happens to return.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support image input")


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

    def recognize_image(self, image_base64: str, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_base64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        return "".join(block.text for block in response.content if block.type == "text")


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

    def recognize_image(self, image_base64: str, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                        },
                    ],
                }
            ],
        )
        return response.choices[0].message.content or ""


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


def get_vision_llm_provider() -> LLMProvider:
    """
    Same idea as get_llm_provider(), but for image-input calls (kanji
    handwriting recognition). Deliberately a separate env var
    (VISION_LLM_PROVIDER, default "anthropic") rather than reusing
    LLM_PROVIDER: DeepSeek -- this project's default chat provider --
    has no vision input, so recognition needs its own, independently
    configurable choice of provider.
    """
    provider_name = os.getenv("VISION_LLM_PROVIDER", "anthropic").lower()
    model = os.getenv("VISION_LLM_MODEL") or _DEFAULT_MODELS.get(provider_name)

    if provider_name == "anthropic":
        return AnthropicProvider(model=model, api_key=os.getenv("ANTHROPIC_API_KEY"))
    elif provider_name == "openai":
        return OpenAICompatibleProvider(model=model, api_key=os.getenv("OPENAI_API_KEY"))
    else:
        raise ValueError(f"VISION_LLM_PROVIDER {provider_name!r} does not support image input")
