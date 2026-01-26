from pathlib import Path
from dotenv import load_dotenv


def load_env() -> None:
    app_env = Path(__file__).resolve().parent / ".env"
    root_env = Path(__file__).resolve().parents[1] / ".env"
    if app_env.exists():
        load_dotenv(app_env)
    if root_env.exists():
        load_dotenv(root_env, override=True)
