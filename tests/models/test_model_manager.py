from __future__ import annotations

from pathlib import Path

from src.models.model_manager import download_model_to_project, find_repo_dirs_in_folder, model_options, resolve_pretrained_load_path


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


def test_find_repo_dirs_in_folder_detects_safe_and_nested_paths(tmp_path):
    expected = {"a/b", "c/d", "e/f"}
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "a__b").mkdir(parents=True)
    (tmp_path / "models" / "c" / "d").mkdir(parents=True)
    (tmp_path / "e__f").mkdir(parents=True)

    found = find_repo_dirs_in_folder(tmp_path, expected)
    assert set(repo_id for repo_id, _ in found) == expected
    assert any(str(path).endswith("models\\a__b") for _, path in found)
    assert any(str(path).endswith("models\\c\\d") for _, path in found)
    assert any(str(path).endswith("e__f") for _, path in found)


def test_resolve_pretrained_load_path_returns_nested_local_snapshot(tmp_path):
    nested = tmp_path / "owner" / "repo"
    nested.mkdir(parents=True)
    # Must meet min_bytes_for_snapshot() so we do not fall through to Hub id.
    (nested / "weights.bin").write_bytes(b"x" * 300_000)
    assert resolve_pretrained_load_path("owner/repo", models_dir=tmp_path) == str(nested.resolve())


def test_resolve_pretrained_load_path_returns_repo_id_when_project_empty(tmp_path):
    """No local snapshot under models_dir: return hub id string for transformers/from_pretrained."""
    assert resolve_pretrained_load_path("z/m", models_dir=tmp_path) == "z/m"


def test_canonical_hub_repo_id_mochi_legacy():
    from src.models.model_manager import canonical_hub_repo_id

    assert canonical_hub_repo_id("genmo/mochi-1.5-final") == "genmo/mochi-1-preview"
    assert canonical_hub_repo_id("Genmo/Mochi-1.5-Final") == "genmo/mochi-1-preview"
    assert canonical_hub_repo_id("genmo/mochi-1-preview") == "genmo/mochi-1-preview"


def test_resolve_pretrained_load_path_mochi_legacy_id_falls_back_to_preview_hub(tmp_path):
    assert resolve_pretrained_load_path("genmo/mochi-1.5-final", models_dir=tmp_path) == "genmo/mochi-1-preview"


def test_resolve_pretrained_load_path_reuses_legacy_mochi_snapshot_folder(tmp_path):
    """Snapshots downloaded under the old Hub id folder name still load for preview."""
    legacy = tmp_path / "genmo__mochi-1.5-final"
    legacy.mkdir(parents=True)
    (legacy / "weights.bin").write_bytes(b"x" * 300_000)
    p = resolve_pretrained_load_path("genmo/mochi-1-preview", models_dir=tmp_path)
    assert Path(p).resolve() == legacy.resolve()


def test_prompt_conditioning_assigns_varied_scene_types():
    from src.content.prompt_conditioning import assign_scene_types

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
    from src.content.brain import ScriptSegment, VideoPackage
    from src.content.storyboard import build_storyboard

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
    from src.speech.audio_fx import AudioPolishConfig, MusicMixConfig, build_music_duck_cmd, build_voice_process_cmd

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

