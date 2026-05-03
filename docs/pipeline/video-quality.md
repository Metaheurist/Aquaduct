# Video quality, native FPS, and clip-duration alignment

This page documents the rendering-side fixes shipped in the
**Video quality & tab redesign** track. It supersedes the FPS / clip-length
discussion that previously lived inside [`docs/pipeline/main.md`](main.md) and
[`docs/pipeline/editor.md`](editor.md).

## Why the old output looked like a flashing slideshow

A trace of the `Two_Sentenced_Horror_Stories` Pro run showed:

- T2V model: `THUDM/CogVideoX-5b` (trained for **8 fps** playback, 49-frame
  cap on the diffusers pipeline).
- User export FPS: **30** (from the Video tab spinner).
- Clip pipeline: encoded the 49 returned frames at 30 fps, so each clip is
  ~1.6 s of motion crammed into the user-fps file. After per-clip equal-T
  audio chunking, the visible motion was a fraction of a second long with
  static padding — i.e. the "stitched motion pictures" effect.

We now fix this with a small native-FPS registry plus a per-clip metadata
sidecar that downstream stages trust.

## `src/models/native_fps.py`

```python
from src.models.native_fps import (
    native_fps_for, encoded_fps_for,
    write_clip_meta, read_clip_meta, clip_duration_seconds,
)

native_fps_for("THUDM/CogVideoX-5b")          # -> 8
native_fps_for("Wan-AI/Wan2.2-T2V-A14B-Diffusers")  # -> 16
native_fps_for("genmo/mochi-1-preview")       # -> 30
native_fps_for("Lightricks/LTX-2")            # -> 24
native_fps_for("tencent/HunyuanVideo")        # -> 24
native_fps_for("cerspense/zeroscope_v2_576w") # -> None  (use user fps)
```

`encoded_fps_for(model_id, *, user_fps, frame_rate_kw)` resolves the actual
fps used when writing the clip mp4. Precedence:

1. Explicit pipeline kwarg `frame_rate` (e.g. LTX-2 sets this in
   [`src/render/clips.py::_video_pipe_kwargs`](../../src/render/clips.py)).
2. Native-fps registry.
3. User export fps.

Override per model with environment variable
`AQUADUCT_NATIVE_FPS_OVERRIDE_<UPPER_SNAKE_REPO>` (e.g.
`AQUADUCT_NATIVE_FPS_OVERRIDE_THUDM__COGVIDEOX_5B=12`).

## Clip metadata sidecar

For every clip mp4 that the T2V/I2V code writes, we now also persist
`<clip>.mp4.meta.json` with the trustworthy timing info:

```json
{
  "model_id": "THUDM/CogVideoX-5b",
  "encoded_fps": 8,
  "num_frames": 49,
  "duration_s": 6.125,
  "native_fps": 8,
  "user_fps": 30,
  "role": "t2v",
  "prompt": "..."
}
```

Both `_try_text_to_video` and `_try_image_to_video` write this sidecar; the
LTX-2 audio-aware export path (`encode_video(...)`) also writes it.

## Spatial AI upscale (export resolution)

**Temporal** quality (raising clip playback fps) is handled by **Smoothness**
([`temporal_smooth.py`](../../src/render/temporal_smooth.py) — FFmpeg `minterpolate` or optional RIFE).

**Spatial** quality (sharper pixels when T2V outputs are smaller than the Video tab
width×height) is handled by [`spatial_upscale.py`](../../src/render/spatial_upscale.py):

- **`spatial_upscale_mode=auto`** on [`VideoSettings`](../../src/core/config.py) runs after
  optional smoothing in [`clips.py`](../../src/render/clips.py) (local runs only), and again in the
  editor for slideshow assets, so low-res clips are super-resolved **before** Lanczos resize + captions.
- Order: **PyTorch Real-ESRGAN** on CUDA when optional deps are installed; else
  **realesrgan-ncnn-vulkan**; else plain resize.
- During **local** `generate_clips`, the pipeline emits progress messages **Spatial upscale clip i/n…** so long SR passes do not look hung ([`main.py`](../../main.py)).
- **API** cloud runs skip this path (preflight warns that `auto` has no effect).

See [Config — spatial upscale env](../reference/config.md#spatial-upscale-environment-optional) and
[`requirements-optional-upscale.txt`](../../requirements-optional-upscale.txt).

## Editor: per-clip duration alignment (no more equal-T chunking)

`src/render/editor.py::assemble_generated_clips_then_concat` accepts a new
optional kwarg:

```python
assemble_generated_clips_then_concat(
    ...,
    clip_durations=[6.125, 5.0, 6.125, ...],
)
```

When provided, each entry sets the slice length for both the corresponding
video clip and the matching audio chunk. When omitted (or any entry is
`<= 0`), the editor falls back in this order:

1. `clip_durations[i]` (caller-supplied, in seconds).
2. `read_clip_meta(clip).duration_s` (sidecar written by the T2V/I2V step).
3. `VideoFileClip.duration` (decoded from the mp4 itself).
4. `total_dur / clip_count` (legacy equal chunk — only if everything above
   fails).

The audio cursor advances by the resolved per-clip duration, so a 6.125 s
CogVideoX clip and a 5.0 s Mochi clip get exactly 6.125 s and 5.0 s of audio
each — captions stay aligned and the final video stops feeling like static
keyframes with a soundtrack glued on top.

## Audio-track length is now `sum(actual_durations)`

[`main.py`](../../main.py) used to align the narration to
`pro_clip_seconds * len(clips)`; with native FPS this drifts whenever the
model honors its trained timing instead of the user's `T`. The Pro
T2V / I2V branch now does:

```python
from src.models.native_fps import clip_duration_seconds

clip_durations = [
    float(clip_duration_seconds(c, fallback=float(T)) or T)
    for c in clip_paths
]
total_T = max(0.5, sum(clip_durations))
```

`total_T` is the value passed to `_ffmpeg_align_wav_to_duration`, and the
same `clip_durations` list is forwarded into
`assemble_generated_clips_then_concat`. The pipeline log line at this stage
now reads e.g. `timeline ≈ 23.50s across 4 clips`, which is the actual
duration users will see in the final mp4.

## Caption closure hygiene

The per-clip caption overlay used to capture the loop variable `t0` by
reference, which produced a subtle late-binding bug whenever clip durations
differed. The new code uses an explicit factory:

```python
def _caption_overlay_factory(t_start, fn):
    def caption_overlay(local_t):
        return fn(t_start + local_t)
    return caption_overlay
```

so each clip's overlay is bound to its own start time.

## Optional temporal smoothing (Phase 2)

Native-fps encoding fixed the timing problem but the *visible* motion still
ticks at the model's frame rate (CogVideoX at 8 fps reads as visibly
"chuggy" against a 30-fps timeline). Phase 2 adds an opt-in motion-aware
upsampling pass driven from `VideoSettings.smoothness_mode`:

| Mode      | Backend                                     | Resource cost                | Quality           |
|-----------|---------------------------------------------|------------------------------|-------------------|
| `off`     | (no-op — default)                           | none                          | identical to legacy |
| `ffmpeg`  | `minterpolate=mci:aobmc:vsbmf=1`            | CPU only, bundled binary     | smooth, occasional warps |
| `rife`    | `rife_ncnn_vulkan_python` (lazy import)     | CPU + ≥1.5 GB free VRAM      | best, requires extra package |

Behaviour summary, all implemented in
[`src/render/temporal_smooth.py`](../../src/render/temporal_smooth.py):

- `target_fps` is clamped to `[12, 60]` and capped per the
  `smoothness_target_fps` Video setting.
- If the resolved target is **≤** the clip's encoded fps, smoothing is a
  no-op (no needless re-encode).
- The original mp4 is replaced atomically; the `.mp4.meta.json` sidecar is
  rewritten so the editor + audio aligner pick up the new fps and frame
  count.
- On any failure the original clip is kept and a `mode_used="off"`
  result is returned — smoothing must never break a successful render.
- `rife` falls back to `ffmpeg` when the package is missing or
  `torch.cuda.mem_get_info()` reports too little headroom (< 1500 MB by
  default; see `RIFE_VRAM_BUDGET_MB`).

`src/render/clips.py::generate_clips` calls
`_maybe_smooth_clips(...)` immediately after the T2V/I2V batch returns, so
all downstream stages (editor, audio align, captions) see the upsampled
mp4s and matching sidecars without further changes.

`src/runtime/preflight.py` now warns up-front when:

- `smoothness_mode == "rife"` is selected in API mode (silently ignored).
- `rife_available()` returns `False` (package missing — falls back to
  ffmpeg).
- Free VRAM is below `RIFE_VRAM_BUDGET_MB` (falls back to ffmpeg).

These warnings appear in the run preflight panel so the user can either
free GPU memory, install the optional package, or simply switch to
`ffmpeg` mode.

## See also

- [`docs/pipeline/editor.md`](editor.md) — overall mux and overlay pipeline.
- [`docs/pipeline/main.md`](main.md) — Pro-mode call sites for T2V / I2V.
- `tests/render/test_native_fps_encode.py`
- `tests/render/test_audio_alignment_real_durations.py`
- `tests/render/test_temporal_smooth.py`
