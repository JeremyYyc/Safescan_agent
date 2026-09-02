import pytest
from pydantic import ValidationError
from app.settings import Settings, ROOT_DIR


def test_precedence_and_secret_redaction(tmp_path):
    # Root source resolution is independent of current working directory.
    assert (ROOT_DIR / 'backend').is_dir()
    s = Settings.from_sources(env_file=None, environ={'AUTH_SECRET': 'private-value', 'AGENT_MAX_CONCURRENCY': '2'}, AGENT_MAX_CONCURRENCY=3)
    assert s.AGENT_MAX_CONCURRENCY == 3
    assert 'private-value' not in repr(s)
    assert s.require_secret('AUTH_SECRET') == 'private-value'


def test_invalid_and_missing_config():
    with pytest.raises(ValidationError):
        Settings(AGENT_MAX_CONCURRENCY=0)
    with pytest.raises(RuntimeError, match='AUTH_SECRET'):
        Settings().require_secret('AUTH_SECRET')


def test_existing_model_policy():
    s = Settings()
    assert [getattr(s, 'ALIBABA_MODEL_' + t) for t in ('L1','L2','L3','VL')] == ['qwen-turbo-latest','qwen-plus-latest','qwen-max-latest','qwen3-vl-plus']


def test_long_video_limits_are_consistent():
    s = Settings()
    assert s.MAX_VIDEO_SECONDS == 6000
    assert s.MAX_UPLOAD_BYTES == 8 * 1024**3
    assert s.MAX_EXTRACTED_FRAMES == 1200
    assert s.VIDEO_FRAME_SAMPLE_RATE == 1.0
    assert s.MAX_EXTRACTED_FRAMES < s.MAX_VIDEO_SECONDS * s.VIDEO_FRAME_SAMPLE_RATE


def test_example_documents_every_setting():
    from dotenv import dotenv_values
    assert set(dotenv_values(ROOT_DIR / '.env.example')) == set(Settings.model_fields)
