from __future__ import annotations

from pathlib import Path

from src.model_manager import download_model_to_project, model_options


def test_model_options_enumerated_and_sorted():
    opts = model_options()
    assert opts
    # orders should restart per kind starting at 1
    kinds = {}
    for o in opts:
        kinds.setdefault(o.kind, []).append(o.order)
    for k, orders in kinds.items():
        assert orders[0] == 1
        assert orders == sorted(orders)


def test_download_model_to_project_calls_snapshot_download(tmp_path, monkeypatch):
    calls = {}

    def fake_snapshot_download(**kwargs):
        calls.update(kwargs)
        return str(tmp_path / "out")

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_snapshot_download, raising=False)
    out = download_model_to_project("repo/id", models_dir=tmp_path)
    assert isinstance(out, Path)
    assert calls["repo_id"] == "repo/id"
    assert "local_dir" in calls


def test_prompt_conditioning_assigns_varied_scene_types():
    from src.prompt_conditioning import assign_scene_types

    prompts = [
        "cyberpunk dashboard UI",
        "infographic chart of performance",
        "timeline over time",
        "portrait of developer",
        "world map overlay",
        "cyberpunk dashboard UI again",
    ]
    types = assign_scene_types(prompts)
    assert len(types) == len(prompts)
    # Best-effort: should not repeat the same type back-to-back for this input.
    for a, b in zip(types, types[1:]):
        assert a != b


def test_storyboard_builds_deterministic_seeds_and_overlay_cap():
    from src.brain import ScriptSegment, VideoPackage
    from src.storyboard import build_storyboard

    pkg = VideoPackage(
        title="T",
        description="D",
        hashtags=["#AI"],
        hook="H",
        segments=[
            ScriptSegment(narration="One", visual_prompt="cyberpunk dashboard UI", on_screen_text="ONE"),
            ScriptSegment(narration="Two 30% faster", visual_prompt="infographic chart stats", on_screen_text="TWO"),
            ScriptSegment(narration="Three", visual_prompt="portrait of developer", on_screen_text="THREE"),
            ScriptSegment(narration="Four", visual_prompt="timeline over time", on_screen_text="FOUR"),
            ScriptSegment(narration="Five", visual_prompt="world map overlay", on_screen_text="FIVE"),
        ],
        cta="C",
    )

    sb1 = build_storyboard(pkg, seed_base=123, max_scenes=5)
    sb2 = build_storyboard(pkg, seed_base=123, max_scenes=5)
    assert [s.seed for s in sb1.scenes] == [s.seed for s in sb2.scenes]
    # overlay cap ~40% of scenes => max 2 overlays for 5 scenes
    overlays = [s.overlay for s in sb1.scenes if s.overlay != "none"]
    assert len(overlays) <= 2


def test_audio_fx_builds_ffmpeg_cmds(tmp_path):
    from src.audio_fx import AudioPolishConfig, MusicMixConfig, build_music_duck_cmd, build_voice_process_cmd

    ffmpeg = tmp_path / "ffmpeg.exe"
    vin = tmp_path / "in.wav"
    vout = tmp_path / "out.wav"
    music = tmp_path / "music.mp3"

    cmd1 = build_voice_process_cmd(ffmpeg=ffmpeg, in_wav=vin, out_wav=vout, cfg=AudioPolishConfig(mode="basic"))
    assert cmd1 and str(ffmpeg) in cmd1[0]
    assert "-af" in cmd1

    cmd2 = build_music_duck_cmd(
        ffmpeg=ffmpeg,
        voice_wav=vin,
        music_path=music,
        out_wav=vout,
        cfg=MusicMixConfig(enabled=True, ducking_enabled=True, fade_s=1.0, music_volume=0.08),
    )
    assert cmd2 and str(ffmpeg) in cmd2[0]
    assert "-filter_complex" in cmd2

