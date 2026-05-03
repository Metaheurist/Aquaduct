# Video tab v2 — four-knob preset model (Phase 5)

The legacy Video tab exposed five raw spinners (`clips_per_video`,
`pro_clip_seconds`, `fps`, `width`, `height`, plus the smoothness toggle
introduced in Phase 2). The trace from `Two_Sentenced_Horror_Stories`
showed users mismatching the values — e.g. picking 30 fps for a model
that natively encodes at 8 fps, which produced the "flashing slideshow"
look. v2 wraps the spinners with **four named presets** plus the existing
smoothness mode and a hidden Advanced disclosure for power users.

| Knob       | Choice key                                  | Drives                                                                |
|------------|---------------------------------------------|-----------------------------------------------------------------------|
| Length     | `short` / `medium` / `long`                  | `clips_per_video`, `pro_clip_seconds`, T2V `length_factor`            |
| Scene      | `punchy` / `balanced` / `cinematic`          | `pro_clip_seconds` (per-clip target)                                  |
| FPS        | `cinematic_24` / `standard_30` / `smooth_60` | `fps`, `smoothness_target_fps`                                        |
| Resolution | `vertical_1080p` / `vertical_720p` / `square_1080` | `width`, `height`                                                |
| Smoothness | `off` / `ffmpeg` / `rife`                    | `smoothness_mode` (Phase 2)                                           |

## Source of truth

[`src/render/video_quality_presets.py`](../../src/render/video_quality_presets.py)
defines the registries (`LENGTH_PRESETS`, `SCENE_PRESETS`, `FPS_PRESETS`,
`RESOLUTION_PRESETS`) and the helpers used everywhere else:

- `length_preset(pid)` / `scene_preset(pid)` / `fps_preset(pid)` /
  `resolution_preset(pid)` — total-of-strings → preset lookups with
  default fall-backs.
- `length_factor_for(settings)` — reads `video_length_preset_id` (off the
  `VideoSettings`) and returns the scalar factor (`0.85` / `1.0` / `1.25`).
- `apply_t2v_length_factor(kwargs, factor)` — rescale a T2V kwargs dict's
  `num_frames` while keeping the **8-frame floor** so a misconfigured
  factor can't ask the pipeline for zero motion.
- `migrate_legacy_video_settings(legacy)` — pick the closest preset id
  for each knob from existing raw values. Idempotent.
- `apply_video_presets(legacy)` — when a preset id is set, override the
  matching raw value(s). Blank id leaves the raw value alone (which is
  how the Advanced disclosure stays useful for power users).

## Pipeline integration

- **Settings load**: `src/settings/ui_settings.py::load_settings_from_data`
  pipes the persisted dict through
  `apply_video_presets(migrate_legacy_video_settings(...))` so on every
  load the preset ids are valid and the raw values match. The new
  `VideoSettings.video_length_preset_id` / `..._scene_preset_id` /
  `..._fps_preset_id` / `..._resolution_preset_id` plus
  `smoothness_mode` and `smoothness_target_fps` round-trip via
  `dataclasses.asdict()`.
- **T2V kwargs**: `src/models/inference_profiles.py::merge_t2v_from_settings`
  applies `length_factor_for(settings.video)` after the per-model VRAM
  profile selection, so picking "long" actually gives the model more
  frames to work with (and "short" gives it fewer).
- **Scene prompts**: `main.py` already forwards
  `video_settings.clips_per_video` (now driven by the Length preset)
  into Phase 4's `_split_into_pro_scenes_from_script`, so the script LLM
  hears the same length intent.
- **Smoothness**: Phase 2 already reads `smoothness_mode` and
  `smoothness_target_fps`; the FPS preset now keeps these in sync so a
  user picking "smooth_60" automatically targets 60 fps for the
  smoothing pass.

## UI

[`UI/tabs/video_tab.py`](../../UI/tabs/video_tab.py) adds a new
**"Quality presets"** form right above **Output & timing**:

```
Length:        Medium clip (~25–35 s)
Scene length:  Balanced scenes
Frame rate:    Standard 30 fps
Resolution:    Vertical 1080×1920
Smoothness:    Off — encode at native fps
```

Picking any combo box snaps the matching legacy spinners
(`fps_spin`, `clips_spin`, `pro_clip_seconds_spin`, `format_combo`)
through the same `_applying_video_template` mutex used by the platform
template tiles, so the user always sees a coherent state. Editing the
spinners directly does *not* reset the v2 presets — that lets advanced
users tweak a single value without losing the rest of the preset.

The selections are persisted via `UI/main_window.py::_settings_from_ui`,
which now writes:

- `smoothness_mode`
- `video_length_preset_id`
- `video_scene_preset_id`
- `video_fps_preset_id`
- `video_resolution_preset_id`

into `VideoSettings(...)` alongside the existing fields. The save flow
already round-trips these through `asdict()` so no further wiring is
needed.

## Tests

[`tests/render/test_video_quality_presets.py`](../../tests/render/test_video_quality_presets.py)
covers (19 cases):

- Each preset registry returns sane values, in order.
- `length_factor_for(...)` reads the right field and falls back to 1.0.
- `apply_t2v_length_factor(...)` scales correctly, clamps to 8 frames
  minimum, no-ops when `num_frames` is missing, and never mutates the
  input dict.
- `migrate_legacy_video_settings(...)` picks short / medium / long /
  punchy / balanced / cinematic / standard_30 / cinematic_24 / smooth_60
  for representative legacy inputs. Idempotent when ids are already set.
- `apply_video_presets(...)` overrides raw values when a preset id is
  present and is a no-op when the id is blank.

## See also

- [`docs/pipeline/video-quality.md`](../pipeline/video-quality.md) —
  Phase 1 native fps and Phase 2 smoothing.
- [`docs/pipeline/scene-prompts.md`](../pipeline/scene-prompts.md) —
  Phase 4 scene-prompt builder which receives `clips_per_video` as the
  scene-count budget.
