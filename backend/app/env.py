from app.settings import get_settings


def load_env() -> None:
    # Transitional compatibility for existing imports; never mutates environment.
    get_settings()
