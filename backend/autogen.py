import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class ConversableAgent:
    """
    Minimal shim for projects that import `from autogen import ConversableAgent`.
    This keeps legacy code running when the real autogen package isn't available.
    """

    def __init__(self, name: Optional[str] = None, llm_config: Optional[Dict[str, Any]] = None, **kwargs: Any):
        self.name = name or kwargs.get("name") or self.__class__.__name__
        self.llm_config = llm_config
        self.kwargs = kwargs


def config_list_from_json(source: str) -> List[Dict[str, Any]]:
    """
    Minimal helper to load a config list from a JSON file path or JSON string.
    """
    if not source:
        return []

    path = Path(source)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

    env_value = os.getenv(source, "")
    if env_value:
        try:
            return json.loads(env_value)
        except Exception:
            return []

    try:
        return json.loads(source)
    except Exception:
        return []


__all__ = ["ConversableAgent", "config_list_from_json"]
