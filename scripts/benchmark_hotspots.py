"""Micro-benchmarks for non-GPU hotspots (startup, settings, library, ranking, chat RAG).

Run from the repo root:  python scripts/benchmark_hotspots.py [--json out.json]

All app data goes to a temporary folder; the real ``.Aquaduct_data`` is never touched.
GPU stages (LLM, diffusion, TTS) are not measured here.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.util.torch_dll_preload import preload_torch_dlls  # noqa: E402

preload_torch_dlls()  # llm_chat_rag pulls in PyQt6; torch must win the DLL race first

_APP_DIR_MODULES = (
    "src.core.app_dirs",
    "src.core.config",
    "src.settings.ui_settings",
    "src.runtime.pipeline_queue_store",
    "src.settings.secrets_crypto",
    "src.content.llm_chat_rag",
)


def _timeit(fn: Callable[[], object], *, repeat: int) -> dict[str, float]:
    samples: list[float] = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return {
        "median_ms": round(statistics.median(samples), 2),
        "min_ms": round(min(samples), 2),
        "max_ms": round(max(samples), 2),
        "runs": repeat,
    }


def _subprocess_import_ms(module: str, repeat: int = 3) -> dict[str, float]:
    code = (
        "import time,importlib;t=time.perf_counter();"
        f"importlib.import_module({module!r});print((time.perf_counter()-t)*1000)"
    )
    samples: list[float] = []
    for _ in range(repeat):
        out = subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=300
        )
        if out.returncode != 0:
            return {"error": (out.stderr.strip().splitlines() or ["failed"])[-1][:160]}  # type: ignore[dict-item]
        samples.append(float(out.stdout.strip().splitlines()[-1]))
    return {"median_ms": round(statistics.median(samples), 1), "min_ms": round(min(samples), 1), "runs": repeat}


def _make_library(videos: Path, n: int) -> None:
    for i in range(n):
        d = videos / f"video_{i:05d}"
        d.mkdir(parents=True)
        (d / "final.mp4").write_bytes(b"\0" * 1024)
        (d / "meta.json").write_text(json.dumps({"title": f"Video {i}", "tags": ["a", "b"]}), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--skip-ui", action="store_true")
    args = ap.parse_args()

    results: dict[str, object] = {"python": sys.version.split()[0], "platform": sys.platform}

    print("cold imports (fresh interpreter each run)...", flush=True)
    results["import"] = {
        m: _subprocess_import_ms(m)
        for m in ("src.core.config", "src.settings.ui_settings", "UI.main_window", "torch", "diffusers")
    }

    tmp = tempfile.TemporaryDirectory(prefix="aq_bench_")
    data = Path(tmp.name) / ".Aquaduct_data"
    data.mkdir(parents=True)
    patches = []
    import importlib

    for name in _APP_DIR_MODULES:
        mod = importlib.import_module(name)
        if hasattr(mod, "application_data_dir"):
            p = mock.patch.object(mod, "application_data_dir", lambda: data)
            p.start()
            patches.append(p)

    try:
        from dataclasses import replace

        from src.core.config import AppSettings
        from src.settings.ui_settings import load_settings, save_settings

        s = replace(AppSettings(), api_openai_key="sk-test-0123456789", firecrawl_api_key="fc-test-0123456789") \
            if hasattr(AppSettings(), "api_openai_key") else AppSettings()
        save_settings(s)
        print("settings save/load...", flush=True)
        results["settings_save"] = _timeit(lambda: save_settings(s), repeat=30)
        results["settings_load"] = _timeit(load_settings, repeat=30)

        from src.settings.secrets_crypto import decrypt_settings_dict, encrypt_settings_dict
        from dataclasses import asdict

        d = asdict(s)
        enc = encrypt_settings_dict(dict(d), data_dir=data)
        results["secrets_encrypt_dict"] = _timeit(lambda: encrypt_settings_dict(dict(d), data_dir=data), repeat=50)
        results["secrets_decrypt_dict"] = _timeit(lambda: decrypt_settings_dict(dict(enc), data_dir=data), repeat=50)

        from src.runtime.pipeline_queue_store import load_pipeline_queue, save_pipeline_queue

        q = [{"kind": "pipeline", "settings": s, "qty": 1} for _ in range(50)]
        print("pipeline queue (50 items)...", flush=True)
        results["queue_save_50"] = _timeit(lambda: save_pipeline_queue(q), repeat=10)
        results["queue_load_50"] = _timeit(load_pipeline_queue, repeat=10)
        results["queue_file_kb"] = round((data / "pipeline_queue.json").stat().st_size / 1024, 1)

        from UI.services.library_fs import scan_finished_videos

        for n in (200, 2000):
            vids = Path(tmp.name) / f"videos_{n}"
            _make_library(vids, n)
            print(f"library scan ({n} folders)...", flush=True)
            results[f"library_scan_{n}"] = _timeit(lambda v=vids: scan_finished_videos(v), repeat=5)

        from src.content.content_quality import score_item
        from src.content.crawler import NewsItem

        seen = [f"Breaking update number {i} on AI chips and model releases from vendor {i % 37}" for i in range(5000)]
        items = [NewsItem(title=f"New AI model {i} beats benchmark on reasoning tasks", url=f"https://x/{i}", source="s")
                 for i in range(300)]
        print("headline ranking (300 items x 200 seen)...", flush=True)
        results["rank_300_headlines"] = _timeit(
            lambda: [score_item(it, topic_tags=["ai", "chips"], seen_titles=seen) for it in items], repeat=5
        )

        from src.content.article_clean import clean_article_excerpt

        para = "This is a sentence about the subject of the article with some detail. " * 40
        big = "\n\n".join([para] * 600)
        results["article_clean_input_kb"] = round(len(big) / 1024)
        results["article_clean_large"] = _timeit(lambda: clean_article_excerpt(big, max_chars=8000), repeat=5)

        from src.models.hardware import rate_model_fit_for_repo, vram_requirement_hint
        from src.models.model_manager import model_options

        opts = model_options()

        def _fit_table() -> None:
            for o in opts:
                k = o.kind if o.kind in ("script", "image", "video", "voice") else "script"
                rate_model_fit_for_repo(kind=k, speed=o.speed, repo_id=o.repo_id, vram_gb=12.0, ram_gb=32.0)
                vram_requirement_hint(kind=k, repo_id=o.repo_id, speed=o.speed)

        results["model_fit_table_rows"] = len(opts)
        results["model_fit_table"] = _timeit(_fit_table, repeat=10)

        from src.content import llm_chat_rag as rag

        with mock.patch.object(rag, "try_make_text_encoder", lambda *_a, **_k: None):
            static = rag.collect_static_snippets()
            results["rag_static_snippets"] = len(static)
            print("chat RAG (BM25 only)...", flush=True)
            results["rag_collect_static"] = _timeit(rag.collect_static_snippets, repeat=3)
            results["rag_build_bm25"] = _timeit(lambda: rag.build_chat_docs_index(static, []), repeat=3)
            idx = rag.build_chat_docs_index(static, [])
            results["rag_search_bm25"] = _timeit(
                lambda: idx.search("how do I queue multiple videos with series mode", k=3), repeat=20
            )

        if not args.skip_ui:
            print("main window construction (offscreen)...", flush=True)
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from PyQt6.QtWidgets import QApplication

            app = QApplication.instance() or QApplication([])
            import UI.main_window as mw
            import UI.workers.models as wm
            import src.util.network_status as ns

            noop = lambda self: None  # noqa: E731
            with mock.patch.object(wm.ModelSizePingWorker, "run", lambda self: self.done.emit({})), \
                 mock.patch.object(ns, "is_internet_likely_reachable", lambda *a, **k: True), \
                 mock.patch.object(mw.MainWindow, "_toast", lambda *a, **k: None, create=True), \
                 mock.patch.object(mw.MainWindow, "_maybe_prompt_hf_token", noop), \
                 mock.patch.object(mw.MainWindow, "_maybe_show_first_run_tutorial", noop), \
                 mock.patch.object(mw.MainWindow, "_start_chat_docs_index_build", noop):
                t0 = time.perf_counter()
                win = mw.MainWindow()
                t1 = time.perf_counter()
                per_tab: dict[str, float] = {}
                while win._deferred_tab_queue:
                    name, attach = win._deferred_tab_queue.pop(0)
                    ta = time.perf_counter()
                    if os.environ.get("AQ_BENCH_PROFILE_TAB") == name:
                        import cProfile
                        import pstats

                        prof = cProfile.Profile()
                        prof.runcall(attach, win)
                        pstats.Stats(prof).sort_stats("cumulative").print_stats(25)
                    else:
                        attach(win)
                    per_tab[name] = round((time.perf_counter() - ta) * 1000, 1)
                win._ensure_all_tabs_built()
                t2 = time.perf_counter()
                results["tab_build_ms"] = per_tab
                app.processEvents()
                results["main_window_ctor_ms"] = round((t1 - t0) * 1000, 1)
                results["main_window_build_all_tabs_ms"] = round((t2 - t1) * 1000, 1)
                t3 = time.perf_counter()
                win._collect_settings_from_ui()
                results["collect_settings_from_ui_ms"] = round((time.perf_counter() - t3) * 1000, 2)
                win.hide()
                win.deleteLater()
                app.processEvents()
    finally:
        for p in patches:
            p.stop()
        tmp.cleanup()

    print(json.dumps(results, indent=2))
    if args.json:
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
