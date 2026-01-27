import os
from typing import Dict
from app.env import load_env

load_env()

MODEL_TIERS = ("L1", "L2", "L3", "VL")

MODEL_ENV_KEYS = {
    "L1": "ALIBABA_MODEL_L1",
    "L2": "ALIBABA_MODEL_L2",
    "L3": "ALIBABA_MODEL_L3",
    "VL": "ALIBABA_MODEL_VL",
}

DEFAULT_PARAMS = {
    "L1": {"temperature": 0.2, "top_p": 0.8},
    "L2": {"temperature": 0.4, "top_p": 0.85},
    "L3": {"temperature": 0.35, "top_p": 0.85},
    "VL": {"temperature": 0.3, "top_p": 0.85},
}


def get_model_name(tier: str) -> str:
    tier = tier.upper()
    if tier not in MODEL_TIERS:
        raise ValueError(f"Unknown model tier: {tier}")

    env_key = MODEL_ENV_KEYS[tier]
    value = os.getenv(env_key)
    if not value:
        raise RuntimeError(f"Missing model env for {tier}: {env_key}")
    return value


def get_generation_params(tier: str) -> Dict[str, float]:
    tier = tier.upper()
    if tier not in MODEL_TIERS:
        raise ValueError(f"Unknown model tier: {tier}")
    return DEFAULT_PARAMS[tier].copy()


def get_max_concurrency(default_value: int = 5) -> int:
    raw = os.getenv("AGENT_MAX_CONCURRENCY")
    if not raw:
        return default_value
    try:
        value = int(raw)
        return value if value > 0 else default_value
    except ValueError:
        return default_value
