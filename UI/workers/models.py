from __future__ import annotations

import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from src.models.model_integrity_cache import classify_integrity_status
from src.models.model_manager import (
    download_model_to_project,
    load_hf_size_cache,
    probe_hf_model,
    save_hf_size_cache,
    verify_project_model_integrity,
)
from src.util.cpu_parallelism import disk_bound_verify_workers, io_bound_pool_workers

from UI.workers.common import _fmt_bytes, _reraise_system_interrupt
from debug import dprint


class FFmpegEnsureWorker(QThread):
    """
    Download static FFmpeg into ``.Aquaduct_data/.cache/ffmpeg`` on first use. Keeps the UI responsive
    (runs off the GUI thread).
    """

    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, ffmpeg_dir: Path):
        super().__init__()
        self.ffmpeg_dir = ffmpeg_dir

    def run(self) -> None:
        try:
            from src.render.utils_ffmpeg import ensure_ffmpeg, find_ffmpeg

            if find_ffmpeg(self.ffmpeg_dir):
                self.finished_ok.emit()
                return
            ensure_ffmpeg(self.ffmpeg_dir)
            self.finished_ok.emit()
        except BaseException as e:
            _reraise_system_interrupt(e)
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class ModelDownloadWorker(QThread):
    # task "download" - overall 0–100 across repos; step 0–100 = current file download
    progress = pyqtSignal(str, int, int, str)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        repo_ids: list[str],
        models_dir,
        title: str = "Downloading",
        remote_bytes_by_repo: dict[str, int] | None = None,
    ):
        super().__init__()
        self.repo_ids = [r for r in repo_ids if r]
        self.models_dir = models_dir
        self.title = title
        self._remote_bytes_by_repo = dict(remote_bytes_by_repo or {})
        self._stop_requested = False
        self._stop_reason: str = "cancelled"  # "cancelled" | "paused"
        self.current_index: int = 0  # 1-based index into repo_ids while running
        self.current_repo_id: str = ""

    def cancel(self) -> None:
        """
        Best-effort cancellation.
        We signal our progress bridge to abort; partial files are left in place so a later run can resume.
        """
        self._stop_requested = True
        self._stop_reason = "cancelled"

    def pause(self) -> None:
        """
        Best-effort pause.
        Same mechanics as cancel, but reported as "Paused" so UI can offer resume semantics.
        """
        self._stop_requested = True
        self._stop_reason = "paused"

    def run(self) -> None:
        try:
            dprint("workers", "ModelDownloadWorker", f"repos={len(self.repo_ids)}", str(self.repo_ids[:5]))
            total_models = max(1, len(self.repo_ids))

            # TQDM bridge to Qt progress
            from tqdm.auto import tqdm
            import time

            worker = self

            class _CancelledDownload(RuntimeError):
                pass

            class QtTqdm(tqdm):  # type: ignore[misc]
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self._last_pct = -1
                    self._last_n = -1
                    self._last_emit_t = 0.0

                def refresh(self, *args, **kwargs):  # noqa: D401
                    try:
                        if worker._stop_requested:
                            raise _CancelledDownload(worker._stop_reason)

                        def _human_bytes(x: float | int | None) -> str:
                            if x is None:
                                return "?"
                            x = float(x)
                            if x < 0:
                                return "?"
                            units = ["B", "KB", "MB", "GB", "TB"]
                            u = 0
                            while x >= 1024.0 and u < len(units) - 1:
                                x /= 1024.0
                                u += 1
                            if u == 0:
                                return f"{int(x)}{units[u]}"
                            return f"{x:.1f}{units[u]}"

                        total = getattr(self, "total", None)
                        n = getattr(self, "n", 0) or 0
                        pct = int((n / float(total)) * 100) if total else 0
                        cur_i = max(1, int(worker.current_index or 1))
                        n_r = max(1, len(worker.repo_ids))

                        # rate (bytes/sec) if known
                        rate = None
                        try:
                            fd = self.format_dict
                            rate = fd.get("rate", None) if isinstance(fd, dict) else None
                        except Exception:
                            rate = None

                        now = time.time()
                        should_emit = False
                        if pct != self._last_pct:
                            should_emit = True
                        # Also emit if bytes advanced, even if percent didn't change (e.g. pct stays 0 when total unknown)
                        if n != self._last_n and (now - self._last_emit_t) >= 0.35:
                            should_emit = True
                        # And emit periodically so rate updates
                        if (now - self._last_emit_t) >= 1.2:
                            should_emit = True

                        if should_emit:
                            self._last_pct = pct
                            self._last_n = n
                            self._last_emit_t = now

                            n_s = _human_bytes(n)
                            total_s = _human_bytes(total) if total else "?"
                            rate_s = (_human_bytes(rate) + "/s") if rate else "?/s"
                            rid = str(worker.current_repo_id or "").strip() or "?"
                            msg = f"[{cur_i}/{n_r}] {rid}\n{n_s} / {total_s}  ·  {rate_s}  ·  file {pct}%"
                            overall = int(((cur_i - 1) + (pct / 100.0)) / n_r * 100)
                            overall = max(0, min(100, overall))
                            worker.progress.emit("download", overall, pct, msg)
                    except Exception:
                        pass
                    return super().refresh(*args, **kwargs)

            for i, repo_id in enumerate(self.repo_ids, start=1):
                self.current_index = int(i)
                self.current_repo_id = str(repo_id or "")

                if self._stop_requested:
                    self.done.emit("Paused" if self._stop_reason == "paused" else "Cancelled")
                    return
                base = int(((i - 1) / total_models) * 100)
                pb = self._remote_bytes_by_repo.get(str(repo_id).strip())
                ps = _fmt_bytes(pb) if pb else ""
                est = f" (~{ps})" if ps else ""
                self.progress.emit("download", base, 0, f"[{i}/{total_models}] {repo_id}{est}")
                try:
                    download_model_to_project(repo_id, models_dir=self.models_dir, tqdm_class=QtTqdm)
                except _CancelledDownload:
                    self.done.emit("Paused" if self._stop_reason == "paused" else "Cancelled")
                    return
                done_ov = int((i / total_models) * 100)
                self.progress.emit("download", min(100, done_ov), 100, f"Downloaded: {repo_id}")

            self.done.emit("Done")
        except BaseException as e:
            _reraise_system_interrupt(e)
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class ModelIntegrityVerifyWorker(QThread):
    """
    Compare local ``models/<repo>/`` files to Hugging Face Hub (per-file checksums).

    Large models can take several minutes (reads full weight files).
    """

    progress = pyqtSignal(str, str)  # repo_id, status line
    # multiline summary for the log; per-repo status for UI (ok / missing / corrupt / …)
    done = pyqtSignal(str, object)
    failed = pyqtSignal(str)

    def __init__(self, *, repo_ids: list[str], models_dir, scope_label: str = ""):
        super().__init__()
        self.repo_ids = [str(r).strip() for r in (repo_ids or []) if str(r).strip()]
        self.models_dir = models_dir
        self.scope_label = str(scope_label or "").strip()

    def run(self) -> None:
        try:
            lines: list[str] = []
            hdr = "Model integrity check (Hugging Face Hub checksums)"
            if self.scope_label:
                hdr += f" - {self.scope_label}"
            lines.append(hdr)

            if not self.repo_ids:
                lines.append("No repository ids to verify.")
                self.done.emit("\n".join(lines), {})
                return

            n = len(self.repo_ids)
            ok_n = 0
            bad_n = 0
            status_by_repo: dict[str, str] = {}
            md = Path(self.models_dir)
            workers = min(disk_bound_verify_workers(), max(1, n))
            if workers > 1 and n > 1:

                def _verify_one(rid: str):
                    return verify_project_model_integrity(rid, models_dir=md)

                with ThreadPoolExecutor(max_workers=workers) as ex:
                    rpts = list(ex.map(_verify_one, self.repo_ids))
            else:
                rpts = [verify_project_model_integrity(rid, models_dir=md) for rid in self.repo_ids]

            for i, (rid, rpt) in enumerate(zip(self.repo_ids, rpts)):
                self.progress.emit(rid, f"[{i + 1}/{n}] Verifying…")
                lines.append(f"--- {rpt.repo_id} ---")
                if rpt.error:
                    lines.append(f"  ERROR: {rpt.error}")
                    status_by_repo[str(rpt.repo_id)] = "error"
                    bad_n += 1
                    continue
                if rpt.ok:
                    rev = rpt.revision or ""
                    if len(rev) > 12:
                        rev_s = f" (rev {rev[:12]}…)"
                    elif rev:
                        rev_s = f" (rev {rev})"
                    else:
                        rev_s = ""
                    lines.append(f"  OK - {rpt.checked_files} file(s) matched{rev_s}")
                    status_by_repo[str(rpt.repo_id)] = "ok"
                    ok_n += 1
                else:
                    bad_n += 1
                    status_by_repo[str(rpt.repo_id)] = classify_integrity_status(rpt)
                    if rpt.missing_paths:
                        lines.append(f"  Missing on disk ({len(rpt.missing_paths)}): " + ", ".join(rpt.missing_paths[:8]))
                        if len(rpt.missing_paths) > 8:
                            lines.append(f"    … +{len(rpt.missing_paths) - 8} more")
                    if rpt.mismatches:
                        lines.append(f"  Hash mismatch / corruption ({len(rpt.mismatches)} file(s)):")
                        for mm in rpt.mismatches[:5]:
                            lines.append(f"    - {mm.get('path','?')} ({mm.get('algorithm','?')})")
                        if len(rpt.mismatches) > 5:
                            lines.append(f"    … +{len(rpt.mismatches) - 5} more")
                    lines.append("  Re-download this model from the Download menu if corruption is suspected.")
                if rpt.warning:
                    lines.append(f"  Note: {rpt.warning}")

            lines.append(f"Summary: {ok_n} ok, {bad_n} failed, {n} total.")
            self.done.emit("\n".join(lines), status_by_repo)
        except BaseException as e:
            _reraise_system_interrupt(e)
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class ModelSizePingWorker(QThread):
    """
    On UI startup: probe each curated repo on Hugging Face (reachability + precise total size).

    Emits ``{repo_id: {"ok": bool, "bytes": int|None, "error": str}}}``.
    Old call sites merged sizes from this; we still persist successful bytes to hf_model_sizes.json.
    """

    done = pyqtSignal(dict)  # {repo_id: {"ok": bool, "bytes": int | None, "error": str}}
    failed = pyqtSignal(str)

    def __init__(self, *, repo_ids: list[str], cache_path):
        super().__init__()
        self.repo_ids = [str(r).strip() for r in (repo_ids or []) if str(r).strip()]
        self.cache_path = cache_path

    def run(self) -> None:
        try:
            merged: dict[str, int] = {}
            try:
                merged = load_hf_size_cache(self.cache_path)
            except Exception:
                merged = {}

            probe: dict[str, dict] = {}

            def _probe_one(rid: str) -> tuple[str, dict, int | None]:
                ok, b, err = probe_hf_model(rid)
                entry = {
                    "ok": bool(ok),
                    "bytes": (int(b) if ok and b is not None else None),
                    "error": (err or "") if not ok else "",
                }
                return str(rid), entry, (int(b) if ok and b is not None else None)

            n_ids = len(self.repo_ids)
            pool = min(io_bound_pool_workers(), max(1, n_ids))
            if pool > 1 and n_ids > 1:
                with ThreadPoolExecutor(max_workers=pool) as ex:
                    futs = [ex.submit(_probe_one, rid) for rid in self.repo_ids]
                    for fut in as_completed(futs):
                        rid, entry, b_ok = fut.result()
                        probe[rid] = entry
                        if entry.get("ok") and b_ok is not None:
                            merged[rid] = int(b_ok)
            else:
                for rid in self.repo_ids:
                    _, entry, b_ok = _probe_one(rid)
                    probe[str(rid)] = entry
                    if entry.get("ok") and b_ok is not None:
                        merged[str(rid)] = int(b_ok)

            try:
                save_hf_size_cache(self.cache_path, merged)
            except Exception:
                pass
            self.done.emit(probe)
        except BaseException as e:
            _reraise_system_interrupt(e)
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")
