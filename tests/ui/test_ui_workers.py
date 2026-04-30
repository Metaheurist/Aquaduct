from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import sys


def _minimal_wav(path: Path) -> None:
    """Tiny placeholder WAV so FFmpeg-oriented stubs do not choke on empty files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
        b"D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    )


@pytest.mark.qt
def test_preview_worker_custom_mode_skips_news_cache(qtbot, monkeypatch):
    from UI.workers import PreviewWorker
    from src.content.brain import ScriptSegment, VideoPackage
    from src.core.config import AppSettings

    import UI.workers.impl as wmod

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
    monkeypatch.setattr(wmod, "enforce_arc", lambda pkg, **kwargs: pkg)
    # Bypass optional API mode + any accidental real LLM loads — PreviewWorker calls these unified helpers.
    monkeypatch.setattr(wmod, "is_api_mode", lambda _app: False)

    def fake_expand_u(**kwargs):
        assert "cats" in kwargs["raw_instructions"]
        return "expanded brief"

    def fake_gsu(**kwargs):
        assert kwargs.get("creative_brief") == "expanded brief"
        assert kwargs["items"][0].get("source") == "custom"
        return fake_generate_script(**kwargs)

    monkeypatch.setattr(wmod, "_expand_brief_unified", fake_expand_u)
    monkeypatch.setattr(wmod, "_generate_script_unified", fake_gsu)

    from src.content.characters_store import Character

    monkeypatch.setattr(
        wmod,
        "resolve_character_for_pipeline",
        lambda *a, **k: Character(id="abcd1234567890abcd", name="Host"),
    )
    monkeypatch.setattr(wmod, "character_context_for_brain", lambda _ch: "")
    monkeypatch.setattr(wmod, "apply_palette_to_prompts", lambda prompts, _branding=None: list(prompts))

    app = AppSettings(run_content_mode="custom", custom_video_instructions="A video about cats")
    w = PreviewWorker(app)
    results: list[tuple] = []
    failures: list[str] = []
    w.done.connect(lambda *a: results.append(tuple(a)))
    w.failed.connect(lambda msg: failures.append(str(msg)))
    w.start()
    qtbot.waitUntil(lambda: not w.isRunning(), timeout=25_000)
    assert not failures, failures
    assert len(results) == 1
    pkg, sources, prompts, personality_id, confidence = results[0]
    assert pkg.title == "T"
    assert sources[0]["source"] == "custom"


def test_run_once_uses_prebuilt_pkg(monkeypatch, tmp_path):
    import main as pipeline_main
    from dataclasses import replace

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
        pictures_dir=ada / "pictures",
        models_dir=ada / "models",
        cache_dir=ada / ".cache",
        ffmpeg_dir=ada / ".cache" / "ffmpeg",
    )
    for d in [
        paths.news_cache_dir,
        paths.runs_dir,
        paths.videos_dir,
        paths.pictures_dir,
        paths.models_dir,
        paths.cache_dir,
        paths.ffmpeg_dir,
    ]:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(pipeline_main, "get_paths", lambda: paths)
    monkeypatch.setattr(pipeline_main, "preflight_check", lambda **kwargs: type("X", (), {"ok": True, "errors": [], "warnings": []})())

    # Ensure we would fail if script generation runs (prebuilt package should skip LLM)
    called = {"n": 0}

    def _fake_facade(_app):
        class _F:
            def generate_script_package(self, **_kwargs):
                called["n"] += 1
                raise AssertionError("generate_script_package should not run when prebuilt_pkg is provided")

        return _F()

    monkeypatch.setattr(pipeline_main, "get_generation_facade", _fake_facade)

    # Stub heavy stages / FFmpeg discovery (video mode forces Pro — needs motion model id + clip stubs).
    monkeypatch.setattr(pipeline_main, "find_ffmpeg", lambda _ffmpeg_dir: True)
    monkeypatch.setattr(
        pipeline_main,
        "ensure_ffmpeg",
        lambda ffmpeg_dir: str(Path(ffmpeg_dir) / ("ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg")),
    )
    monkeypatch.setattr(pipeline_main, "prepare_for_next_model", lambda *_a, **_k: None)

    def _fake_syn(**kwargs):
        _minimal_wav(Path(kwargs["out_wav_path"]))
        captions = Path(kwargs["out_captions_json"])
        captions.parent.mkdir(parents=True, exist_ok=True)
        captions.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(pipeline_main, "synthesize", _fake_syn)
    monkeypatch.setattr(pipeline_main, "process_voice_wav", lambda **kwargs: kwargs["in_wav"])
    monkeypatch.setattr(pipeline_main, "generate_images", lambda **kwargs: [])
    monkeypatch.setattr(pipeline_main, "assemble_microclips_then_concat", lambda **kwargs: None)

    def _fake_assemble(**kwargs):
        p = Path(kwargs["out_final_mp4"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"")

    monkeypatch.setattr(pipeline_main, "assemble_generated_clips_then_concat", _fake_assemble)

    def _fake_cast(**_kwargs):
        raise RuntimeError("test: skip cast LLM")

    monkeypatch.setattr(pipeline_main, "generate_cast_from_storyline_llm", _fake_cast)

    class _FakeClip:
        def __init__(self, p: Path) -> None:
            self.path = p

    def _fake_gen_clips(**kwargs):
        out = Path(kwargs["out_dir"])
        out.mkdir(parents=True, exist_ok=True)
        p = out / "stub_clip.mp4"
        p.write_bytes(b"")
        return [_FakeClip(p)]

    monkeypatch.setattr(pipeline_main, "generate_clips", _fake_gen_clips)

    pkg = VideoPackage(
        title="T",
        description="D",
        hashtags=["#AI"],
        hook="H",
        segments=[ScriptSegment(narration="N", visual_prompt="V", on_screen_text="O")],
        cta="C",
    )

    out = pipeline_main.run_once(
        settings=replace(AppSettings(), video_model_id="dummy/T2V-test-stub"),
        prebuilt_pkg=pkg,
        prebuilt_sources=[{"title": "x", "url": "u", "source": "s"}],
        prebuilt_prompts=["V"],
        prebuilt_seeds=[123],
    )

    assert called["n"] == 0
    assert out is not None

