from pathlib import Path
from dotenv import load_dotenv


def load_env() -> None:
    app_env = Path(__file__).resolve().parent / ".env"
    root_env = Path(__file__).resolve().parents[1] / ".env"
    if app_env.exists():
        load_dotenv(app_env)
    if root_env.exists():
        # Keep container/runtime-provided env vars (e.g. docker compose env_file)
        # as the source of truth in deployment.
        load_dotenv(root_env)
