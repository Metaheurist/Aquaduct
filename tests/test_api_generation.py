from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.config import ApiModelRuntimeSettings, ApiRoleConfig, AppSettings
from src.platform.replicate_client import ReplicateRequestError
from src.runtime import api_generation as ag


def test_download_url_to_file(tmp_path):
    dest = tmp_path / "x.bin"
    mock_r = MagicMock()
    mock_r.raise_for_status = MagicMock()
    mock_r.content = b"hello"
    with patch("src.runtime.api_generation.requests.get", return_value=mock_r) as get:
        ag.download_url_to_file("https://example.com/f", dest)
    get.assert_called_once()
    assert dest.read_bytes() == b"hello"


def test_generate_still_unsupported_provider():
    s = AppSettings(
        model_execution_mode="api",
        api_models=ApiModelRuntimeSettings(image=ApiRoleConfig(provider="unknown", model="x")),
    )
    with pytest.raises(RuntimeError, match="Unsupported"):
        ag.generate_still_png_bytes(settings=s, prompt="a cat")


def test_generate_still_replicate_missing_token(monkeypatch):
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    monkeypatch.delenv("REPLICATE_API_KEY", raising=False)
    s = AppSettings(
        model_execution_mode="api",
        api_models=ApiModelRuntimeSettings(image=ApiRoleConfig(provider="replicate", model="ver1")),
    )
    with pytest.raises(ReplicateRequestError, match="token missing"):
        ag.generate_still_png_bytes(settings=s, prompt="x")


def test_generate_still_openai_uses_client(monkeypatch):
    s = AppSettings(
        model_execution_mode="api",
        api_openai_key="sk-test",
        api_models=ApiModelRuntimeSettings(image=ApiRoleConfig(provider="openai", model="dall-e-3")),
    )
    fake = MagicMock()
    fake.download_image_png.return_value = b"\x89PNG\r\n\x1a\n"
    with patch("src.runtime.api_generation.build_openai_client_from_settings", return_value=fake):
        out = ag.generate_still_png_bytes(settings=s, prompt="vertical still")
    assert out.startswith(b"\x89PNG")
    fake.download_image_png.assert_called_once()


def test_replicate_video_mp4_paths_requires_replicate_provider(tmp_path):
    s = AppSettings(
        api_models=ApiModelRuntimeSettings(video=ApiRoleConfig(provider="openai", model="x")),
    )
    with pytest.raises(ReplicateRequestError, match="Replicate video"):
        ag.replicate_video_mp4_paths(settings=s, prompts=["a"], out_dir=tmp_path / "clips")
