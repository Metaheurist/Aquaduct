from __future__ import annotations

import pytest


@pytest.mark.qt
def test_pipeline_batch_worker_emits_done_when_no_items(qtbot, monkeypatch):
    from UI.workers import PipelineBatchWorker
    from src.config import AppSettings

    # Force run_once to always return None
    import UI.workers as wmod

    monkeypatch.setattr(wmod.pipeline_main, "run_once", lambda **kwargs: None)

    w = PipelineBatchWorker(AppSettings(), quantity=2)
    done_msgs = []
    w.done.connect(lambda msg: done_msgs.append(msg))
    w.start()
    qtbot.waitSignal(w.done, timeout=8000)
    qtbot.waitUntil(lambda: len(done_msgs) == 1, timeout=8000)
    assert "No new items" in done_msgs[0] or "Ran out" in done_msgs[0]


def test_run_once_uses_prebuilt_pkg(monkeypatch, tmp_path):
    import main as pipeline_main
    from src.brain import VideoPackage, ScriptSegment
    from src.config import AppSettings, Paths

    # Avoid touching real repo folders
    paths = Paths(
        root=tmp_path,
        data_dir=tmp_path / "data",
        news_cache_dir=tmp_path / "data" / "news_cache",
        runs_dir=tmp_path / "runs",
        videos_dir=tmp_path / "videos",
        models_dir=tmp_path / "models",
        cache_dir=tmp_path / ".cache",
        ffmpeg_dir=tmp_path / ".cache" / "ffmpeg",
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

