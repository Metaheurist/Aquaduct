# Performance notes

Practical import-time review (not a full GPU frame-time study). Measurements were taken on **Windows** with the project **`.venv`** (Python 3.12), using `cProfile` around a single `importlib.import_module(...)` call. Wall times vary with disk cache, antivirus, and installed wheels.

## Method

```powershell
cd <repo>
.\.venv\Scripts\activate
python -c "import cProfile, pstats, io; pr=cProfile.Profile(); pr.enable(); import importlib; importlib.import_module('NAME'); pr.disable(); s=io.StringIO(); pstats.Stats(pr, stream=s).sort_stats('cumtime').print_stats(20); print(s.getvalue())"
```

Replace `NAME` with `main`, `src.runtime.pipeline_api`, or `UI.app`.

## Results (representative cold import)

| Scenario | Approx. wall | Dominant own-time modules (cumtime) |
|----------|--------------|--------------------------------------|
| `import main` | ~1.1 s | `main` → `src/render/editor.py` → **moviepy** (`moviepy.editor`, `VideoFileClip`, `AudioFileClip`); `src/content/story_context.py`; **requests** |
| `import src.runtime.pipeline_api` | ~1.0 s | `pipeline_api` → `src/render/editor.py` (moviepy chain) → `src/content/brain_api.py` → `src/platform/openai_client.py` → **requests** |
| `import UI.app` | ~1.2 s | `UI.app` → **`UI/main_window.py`** → `UI/tabs/__init__.py` (tab imports) → **`UI/tabs/characters_tab.py`** → `src/content/crawler.py` → **`UI/workers.py`** → **`main`** (again pulls editor/moviepy) |

## Takeaways

1. **MoviePy / editor** — Importing `src.render.editor` (and anything that imports `moviepy.editor` eagerly) dominates CLI and API pipeline import paths. This is expected for a video app; deferring or lazy-importing moviepy inside hot paths would shrink *incremental* import graphs but is a larger refactor.
2. **UI cold start** — `UI.main_window` plus **all tabs** loaded at import time accounts for a large share of desktop startup before the event loop runs. Tab code pulls crawler/workers and transitively `main` / editor again.
3. **`run_once_api`** — Not separately profiled here; it lives in `src.runtime.pipeline_api` and reuses the same render/brain stack as local runs. First call cost is dominated by **network I/O** and any **lazy** local imports (e.g. torch) on first model touch, not by the `run_once_api` function wrapper itself.

## “Won’t fix” in the short term

- **First torch / diffusers / transformers load** — Large GPU RAM and seconds of startup when a local model is first materialized; normal for HF stacks.
- **FFmpeg download** — One-time network + disk cost under `.cache/ffmpeg/` (see [ffmpeg.md](ffmpeg.md)).

## Related

- Desktop UX (wheel guard, tabs): [ui.md](ui.md)
- Build + import smoke for frozen EXEs: [building_windows_exe.md](building_windows_exe.md), [`../build/README.md`](../build/README.md)
