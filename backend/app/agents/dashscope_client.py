from __future__ import annotations

import asyncio
from typing import Any, Mapping, Optional, Sequence

from openai import OpenAI

from autogen_core import Image
from autogen_core.models import (
    ChatCompletionClient,
    CreateResult,
    LLMMessage,
    ModelFamily,
    ModelInfo,
    RequestUsage,
)
from autogen_core.tools import Tool, ToolSchema


class DashScopeChatCompletionClient(ChatCompletionClient):
    """
    Minimal ChatCompletionClient using OpenAI-compatible DashScope endpoint.
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str,
        temperature: float,
        top_p: float,
        vision: bool = False,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._top_p = top_p
        self._vision = vision
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._usage = RequestUsage(prompt_tokens=0, completion_tokens=0)

    @property
    def model_info(self) -> ModelInfo:
        return {
            "vision": self._vision,
            "function_calling": False,
            "json_output": True,
            "structured_output": False,
            "family": ModelFamily.UNKNOWN,
        }

    @property
    def capabilities(self) -> dict:
        return {
            "vision": self._vision,
            "function_calling": False,
            "json_output": True,
        }

    async def create(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[Tool | ToolSchema] = [],
        tool_choice: Tool | str = "auto",
        json_output: Optional[bool | type] = None,
        extra_create_args: Mapping[str, Any] = {},
        cancellation_token: Optional[Any] = None,
    ) -> CreateResult:
        if tools:
            raise ValueError("DashScopeChatCompletionClient does not support tool calls in this project.")

        payload = self._convert_messages(messages)
        response = await asyncio.to_thread(
            self._client.chat.completions.create,
            model=self._model,
            messages=payload,
            temperature=self._temperature,
            top_p=self._top_p,
            **dict(extra_create_args),
        )

        content = ""
        if response and response.choices:
            content = response.choices[0].message.content or ""

        usage = response.usage
        if usage:
            self._usage = RequestUsage(
                prompt_tokens=usage.prompt_tokens or 0,
                completion_tokens=usage.completion_tokens or 0,
            )

        return CreateResult(
            finish_reason="stop",
            content=content,
            usage=self._usage,
            cached=False,
        )

    def create_stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[Tool | ToolSchema] = [],
        tool_choice: Tool | str = "auto",
        json_output: Optional[bool | type] = None,
        extra_create_args: Mapping[str, Any] = {},
        cancellation_token: Optional[Any] = None,
    ):
        async def _gen():
            result = await self.create(
                messages,
                tools=tools,
                tool_choice=tool_choice,
                json_output=json_output,
                extra_create_args=extra_create_args,
                cancellation_token=cancellation_token,
            )
            yield result.content
            yield result

        return _gen()

    async def close(self) -> None:
        return None

    def actual_usage(self) -> RequestUsage:
        return self._usage

    def total_usage(self) -> RequestUsage:
        return self._usage

    def count_tokens(self, messages: Sequence[LLMMessage], *, tools: Sequence[Tool | ToolSchema] = []) -> int:
        return 0

    def remaining_tokens(self, messages: Sequence[LLMMessage], *, tools: Sequence[Tool | ToolSchema] = []) -> int:
        return 100000

    def _convert_messages(self, messages: Sequence[LLMMessage]) -> list[dict]:
        converted: list[dict] = []
        for msg in messages:
            if msg.type == "SystemMessage":
                converted.append({"role": "system", "content": msg.content})
            elif msg.type == "UserMessage":
                converted.append({"role": "user", "content": self._convert_content(msg.content)})
            elif msg.type == "AssistantMessage":
                converted.append({"role": "assistant", "content": msg.content})
            elif msg.type == "FunctionExecutionResultMessage":
                converted.append({"role": "tool", "content": str(msg.content)})
        return converted

    def _convert_content(self, content: Any) -> Any:
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, Image):
                    parts.append(item.to_openai_format())
                elif isinstance(item, str):
                    parts.append({"type": "text", "text": item})
                else:
                    parts.append({"type": "text", "text": str(item)})
            return parts
        return content
