from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.qt
def test_preview_worker_custom_mode_skips_news_cache(qtbot, monkeypatch):
    from UI.workers import PreviewWorker
    from src.content.brain import ScriptSegment, VideoPackage
    from src.core.config import AppSettings

    import UI.workers as wmod

    monkeypatch.setattr(wmod, "get_scored_items", lambda *a, **k: (_ for _ in ()).throw(AssertionError("news cache should not load")))
    monkeypatch.setattr(wmod, "get_latest_items", lambda *a, **k: (_ for _ in ()).throw(AssertionError("news cache should not load")))

    def fake_paths():
        root = Path("/tmp/aquaduct_preview_test")
        return SimpleNamespace(news_cache_dir=root / "news_cache", videos_dir=root / "videos")

    monkeypatch.setattr(wmod.pipeline_main, "get_paths", fake_paths)
    monkeypatch.setattr(
        wmod.pipeline_main,
        "get_models",
        lambda: SimpleNamespace(llm_id="m", sdxl_turbo_id="i", kokoro_id="k"),
    )

    def fake_expand(**kwargs):
        assert "cats" in kwargs["raw_instructions"]
        return "expanded brief"

    def fake_generate_script(**kwargs):
        assert kwargs.get("creative_brief") == "expanded brief"
        assert kwargs["items"][0].get("source") == "custom"
        return VideoPackage(
            title="T",
            description="D",
            hashtags=["#AI"],
            hook="H",
            segments=[ScriptSegment(narration="N", visual_prompt="V", on_screen_text="O")],
            cta="C",
        )

    monkeypatch.setattr(wmod, "expand_custom_video_instructions", fake_expand)
    monkeypatch.setattr(wmod, "generate_script", fake_generate_script)
    monkeypatch.setattr(wmod, "enforce_arc", lambda pkg: pkg)

    app = AppSettings(run_content_mode="custom", custom_video_instructions="A video about cats")
    w = PreviewWorker(app)
    results: list[tuple] = []
    w.done.connect(lambda *a: results.append(tuple(a)))
    w.start()
    qtbot.waitUntil(lambda: len(results) >= 1, timeout=8000)
    assert len(results) == 1
    pkg, sources, prompts, personality_id, confidence = results[0]
    assert pkg.title == "T"
    assert sources[0]["source"] == "custom"


def test_run_once_uses_prebuilt_pkg(monkeypatch, tmp_path):
    import main as pipeline_main
    from src.content.brain import VideoPackage, ScriptSegment
    from src.core.config import AppSettings, Paths

    # Avoid touching real repo folders
    ada = tmp_path / ".Aquaduct_data"
    paths = Paths(
        root=tmp_path,
        app_data_dir=ada,
        data_dir=ada / "data",
        news_cache_dir=ada / "data" / "news_cache",
        runs_dir=ada / "runs",
        videos_dir=ada / "videos",
        models_dir=ada / "models",
        cache_dir=ada / ".cache",
        ffmpeg_dir=ada / ".cache" / "ffmpeg",
    )
    for d in [paths.news_cache_dir, paths.runs_dir, paths.videos_dir, paths.models_dir, paths.cache_dir, paths.ffmpeg_dir]:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(pipeline_main, "get_paths", lambda: paths)
    monkeypatch.setattr(pipeline_main, "preflight_check", lambda **kwargs: type("X", (), {"ok": True, "errors": [], "warnings": []})())

    # Ensure we would fail if generate_script is called
    called = {"n": 0}

    def _boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("generate_script should not be called when prebuilt_pkg is provided")

    monkeypatch.setattr(pipeline_main, "generate_script", _boom)

    # Stub heavy stages
    monkeypatch.setattr(pipeline_main, "synthesize", lambda **kwargs: None)
    # Avoid ensure_ffmpeg(): process_voice_wav() would download FFmpeg into tmp ffmpeg_dir (minutes, looks hung).
    monkeypatch.setattr(pipeline_main, "process_voice_wav", lambda **kwargs: kwargs["in_wav"])
    monkeypatch.setattr(pipeline_main, "generate_images", lambda **kwargs: [])
    monkeypatch.setattr(pipeline_main, "assemble_microclips_then_concat", lambda **kwargs: None)

    pkg = VideoPackage(
        title="T",
        description="D",
        hashtags=["#AI"],
        hook="H",
        segments=[ScriptSegment(narration="N", visual_prompt="V", on_screen_text="O")],
        cta="C",
    )

    out = pipeline_main.run_once(
        settings=AppSettings(),
        prebuilt_pkg=pkg,
        prebuilt_sources=[{"title": "x", "url": "u", "source": "s"}],
        prebuilt_prompts=["V"],
        prebuilt_seeds=[123],
    )

    assert called["n"] == 0
    assert out is not None

