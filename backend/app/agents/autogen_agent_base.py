from __future__ import annotations

from typing import Any, Dict
import json
import os
import re

import asyncio
from pathlib import Path

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import MultiModalMessage, TextMessage
from autogen_core import Image

from app.env import load_env
from app.llm_registry import get_model_name, get_generation_params
from app.agents.dashscope_client import DashScopeChatCompletionClient


DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

load_env()


class AutoGenDashscopeAgent:
    """
    Helper base for AutoGen-backed agents using DashScope OpenAI-compatible endpoint.
    """

    def __init__(self, name: str, model_tier: str = "L2") -> None:
        self.name = name
        self.model_tier = (model_tier or "L2").upper()
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")

    def _llm_config(self, tier: str | None = None) -> Dict[str, Any]:
        tier = (tier or self.model_tier).upper()
        model = get_model_name(tier)
        params = get_generation_params(tier)
        return {
            "model": model,
            "temperature": params["temperature"],
            "top_p": params["top_p"],
        }

    def _model_client(self, tier: str | None = None, vision: bool = False) -> DashScopeChatCompletionClient:
        config = self._llm_config(tier)
        return DashScopeChatCompletionClient(
            model=config["model"],
            api_key=self.api_key,
            base_url=DASHSCOPE_BASE_URL,
            temperature=config["temperature"],
            top_p=config["top_p"],
            vision=vision,
        )

    def _create_assistant(
        self,
        system_message: str,
        tier: str | None = None,
        name_suffix: str | None = None,
    ) -> AssistantAgent:
        suffix = f"-{name_suffix}" if name_suffix else ""
        return AssistantAgent(
            name=f"{self.name}{suffix}",
            system_message=system_message,
            model_client=self._model_client(tier, vision=(tier or self.model_tier).upper() == "VL"),
        )

    def _call_llm(
        self,
        system_message: str,
        user_content: Any,
        tier: str | None = None,
        name_suffix: str | None = None,
    ) -> str:
        assistant = self._create_assistant(system_message, tier=tier, name_suffix=name_suffix)
        task = self._build_task_message(user_content)
        reply = self._run_agent_sync(assistant, task)
        return self._extract_content(reply)

    async def _call_llm_async(
        self,
        system_message: str,
        user_content: Any,
        tier: str | None = None,
        name_suffix: str | None = None,
    ) -> str:
        assistant = self._create_assistant(system_message, tier=tier, name_suffix=name_suffix)
        task = self._build_task_message(user_content)
        reply = await assistant.run(task=task)
        return self._extract_content(reply)

    def _run_agent_sync(self, agent: AssistantAgent, task: TextMessage | MultiModalMessage | str) -> Any:
        async def _runner():
            return await agent.run(task=task)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            raise RuntimeError("Synchronous LLM call in running event loop. Use _call_llm_async instead.")

        return asyncio.run(_runner())

    def _build_task_message(self, user_content: Any) -> TextMessage | MultiModalMessage | str:
        if isinstance(user_content, list):
            content_parts = []
            for item in user_content:
                if isinstance(item, dict) and item.get("type") == "image_url":
                    url = item.get("image_url", {}).get("url")
                    if isinstance(url, str) and url.startswith("file://"):
                        path = Path(url[7:])
                        try:
                            content_parts.append(Image.from_file(path))
                            continue
                        except Exception:
                            pass
                    if isinstance(url, str):
                        try:
                            content_parts.append(Image.from_uri(url))
                            continue
                        except Exception:
                            content_parts.append(str(url))
                            continue
                if isinstance(item, dict) and item.get("type") == "text":
                    content_parts.append(str(item.get("text", "")))
                    continue
                content_parts.append(str(item))
            return MultiModalMessage(content=content_parts, source="user")
        return str(user_content)

    @staticmethod
    def _extract_content(reply: Any) -> str:
        if isinstance(reply, str):
            return reply
        if hasattr(reply, "messages"):
            messages = reply.messages
            if messages:
                last = messages[-1]
                content = getattr(last, "content", None)
                if isinstance(content, list):
                    return " ".join([str(item) for item in content])
                if content is not None:
                    return str(content)
        if isinstance(reply, dict):
            if "content" in reply:
                return str(reply["content"])
            if "message" in reply:
                return str(reply["message"])
        return str(reply)

    @staticmethod
    def parse_json_response(response: str) -> Dict[str, Any]:
        cleaned_response = response.strip() if isinstance(response, str) else str(response)

        if cleaned_response.startswith("```json"):
            cleaned_response = cleaned_response[7:]
        if cleaned_response.startswith("```"):
            cleaned_response = cleaned_response[3:]
        if cleaned_response.endswith("```"):
            cleaned_response = cleaned_response[:-3]

        cleaned_response = cleaned_response.strip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            json_match = re.search(r"\{.*\}", cleaned_response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    raise ValueError(f"Could not parse JSON from response: {response}")
            raise ValueError(f"Could not parse JSON from response: {response}")
