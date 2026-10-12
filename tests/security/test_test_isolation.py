"""UI test fixtures must keep every app-data writer inside the temp root (never the real .Aquaduct_data)."""

from __future__ import annotations

from pathlib import Path


def test_write_ui_settings_redirects_all_app_data_writers(write_ui_settings, tmp_repo_root: Path) -> None:
    write_ui_settings({"topic_tags": []})

    from src.core import config
    from src.runtime.pipeline_queue_store import store_path
    from src.settings import secrets_crypto
    from src.settings.ui_settings import settings_path

    assert config.get_paths().app_data_dir == tmp_repo_root
    assert settings_path().parent == tmp_repo_root
    assert store_path().parent == tmp_repo_root
    assert secrets_crypto._key_path().parent == tmp_repo_root
