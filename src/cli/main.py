"""Dispatch CLI subcommands; return process exit code."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.cli.parser import build_parser
from src.cli.settings_merge import merge_partial_app_settings
from src.core.config import AppSettings
from src.core.models_dir import models_dir_for_app
from src.models.model_manager import download_model_to_project, local_model_size_label, model_has_local_snapshot, model_options
from src.runtime.preflight import preflight_check
from src.settings.ui_settings import app_settings_from_dict, load_settings, settings_path


EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INTERNAL = 2


def _apply_hf_token_env(settings: AppSettings) -> None:
    if settings and bool(getattr(settings, "hf_api_enabled", True)):
        saved_token = str(getattr(settings, "hf_token", "") or "").strip()
        if saved_token and not (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN")):
            os.environ["HF_TOKEN"] = saved_token
            os.environ["HUGGINGFACEHUB_API_TOKEN"] = saved_token


def _load_merge_json(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"merge-json not found: {p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("merge-json must be a JSON object at the root.")
    return raw


def _prepare_settings(*, merge_json: str, music: str) -> AppSettings:
    base = load_settings()
    if merge_json.strip():
        partial = _load_merge_json(merge_json.strip())
        base = merge_partial_app_settings(base, partial)
    _apply_hf_token_env(base)
    if (music or "").strip():
        from dataclasses import replace

        base = replace(base, background_music_path=str(Path(music.strip()).resolve()))
    return base


def _redact_settings_dict(d: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(d))  # deep copy via JSON
    secret_keys = (
        "hf_token",
        "api_openai_key",
        "api_replicate_token",
        "firecrawl_api_key",
        "elevenlabs_api_key",
        "tiktok_client_secret",
        "tiktok_access_token",
        "tiktok_refresh_token",
        "youtube_client_secret",
        "youtube_access_token",
        "youtube_refresh_token",
    )
    for k in secret_keys:
        if k in out and out[k]:
            out[k] = "***"
    # nested api_models
    am = out.get("api_models")
    if isinstance(am, dict):
        for role in ("llm", "image", "video", "voice"):
            if role in am and isinstance(am[role], dict):
                for sk in ("org_id",):
                    if am[role].get(sk):
                        am[role][sk] = "***"
    return out


def _run_pipeline(app: AppSettings) -> Path | None:
    from main import run_once

    return run_once(settings=app)


def cmd_run(args: Any) -> int:
    try:
        app = _prepare_settings(merge_json=getattr(args, "merge_json", "") or "", music=getattr(args, "music", "") or "")
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"Error loading settings: {e}", file=sys.stderr)
        return EXIT_ERROR

    pf = preflight_check(settings=app, strict=True)
    for w in pf.warnings:
        print(f"Warning: {w}", file=sys.stderr)
    if not pf.ok:
        print("Preflight failed:", file=sys.stderr)
        for e in pf.errors:
            print(f"  {e}", file=sys.stderr)
        return EXIT_ERROR

    if getattr(args, "dry_run", False):
        print("Dry run: preflight OK.", file=sys.stderr)
        return EXIT_OK

    if args.once:
        try:
            out = _run_pipeline(app)
        except Exception as e:
            print(f"Run failed: {e}", file=sys.stderr)
            return EXIT_ERROR
        if out:
            print(out)
        else:
            print("No new items found.")
        return EXIT_OK

    # watch
    interval_s = max(60.0, float(args.interval_hours) * 3600.0)
    while True:
        try:
            app = _prepare_settings(
                merge_json=getattr(args, "merge_json", "") or "",
                music=getattr(args, "music", "") or "",
            )
            pf2 = preflight_check(settings=app, strict=True)
            if not pf2.ok:
                print("Preflight failed:", file=sys.stderr)
                for e in pf2.errors:
                    print(f"  {e}", file=sys.stderr)
                return EXIT_ERROR
            out = _run_pipeline(app)
            if out:
                print(out)
            else:
                print("No new items found.")
        except Exception as e:
            print(f"Run failed: {e}", file=sys.stderr)
        time.sleep(interval_s)


def cmd_preflight() -> int:
    app = load_settings()
    _apply_hf_token_env(app)
    pf = preflight_check(settings=app, strict=True)
    for w in pf.warnings:
        print(f"Warning: {w}", file=sys.stderr)
    if not pf.ok:
        for e in pf.errors:
            print(e, file=sys.stderr)
        return EXIT_ERROR
    print("Preflight OK.", file=sys.stderr)
    return EXIT_OK


def cmd_config_show(args: Any) -> int:
    app = load_settings()
    d = asdict(app)
    if getattr(args, "no_secrets", False):
        d = _redact_settings_dict(d)
    if getattr(args, "pretty", False):
        print(json.dumps(d, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(d, ensure_ascii=False))
    return EXIT_OK


def cmd_config_path() -> int:
    print(settings_path().resolve())
    return EXIT_OK


def cmd_config_validate(args: Any) -> int:
    try:
        p = settings_path()
        if not p.exists():
            print(f"Settings file missing: {p}", file=sys.stderr)
            return EXIT_ERROR
        data = json.loads(p.read_text(encoding="utf-8"))
        app_settings_from_dict(data)
    except Exception as e:
        print(f"Invalid settings: {e}", file=sys.stderr)
        return EXIT_ERROR
    if getattr(args, "preflight", False):
        app = load_settings()
        _apply_hf_token_env(app)
        pf = preflight_check(settings=app, strict=True)
        for w in pf.warnings:
            print(f"Warning: {w}", file=sys.stderr)
        if not pf.ok:
            for e in pf.errors:
                print(e, file=sys.stderr)
            return EXIT_ERROR
    print("OK.", file=sys.stderr)
    return EXIT_OK


def cmd_models_list() -> int:
    app = load_settings()
    _apply_hf_token_env(app)
    ms = models_dir_for_app(app)
    for opt in model_options():
        snap = model_has_local_snapshot(opt.repo_id, models_dir=ms)
        sz = local_model_size_label(opt.repo_id, models_dir=ms)
        status = "on-disk" if snap else "missing"
        print(f"{opt.kind:7}  {opt.speed:8}  {status:8}  {sz:12}  {opt.repo_id}")
    return EXIT_OK


def cmd_models_download(args: Any) -> int:
    app = load_settings()
    _apply_hf_token_env(app)
    ms = models_dir_for_app(app)
    role = str(getattr(args, "role", "all") or "all")
    override = str(getattr(args, "repo_id", "") or "").strip()

    opts = model_options()
    if override:
        allowed = {o.repo_id for o in opts}
        if override not in allowed:
            print(f"Unknown repo-id (not in curated list): {override}", file=sys.stderr)
            return EXIT_ERROR
        repos = [override]
    elif role == "all":
        repos = list(dict.fromkeys(o.repo_id for o in opts))
    else:
        repos = [o.repo_id for o in opts if o.kind == role]

    for rid in repos:
        print(f"Downloading {rid} …", file=sys.stderr)
        try:
            download_model_to_project(rid, models_dir=ms, tqdm_class=None)
        except Exception as e:
            print(f"Failed {rid}: {e}", file=sys.stderr)
            return EXIT_ERROR
    print("Done.", file=sys.stderr)
    return EXIT_OK


def cmd_tasks_list() -> int:
    from src.platform.upload_tasks import load_tasks

    tasks = load_tasks()
    if not tasks:
        print("(no tasks)", file=sys.stderr)
        return EXIT_OK
    for t in tasks:
        print(f"{t.created_at[:19] if t.created_at else '?'}  {t.status:10}  {t.title[:80]}")
        print(f"  {t.video_dir}")
    return EXIT_OK


def cmd_version() -> int:
    from src.cli import CLI_VERSION

    print(f"aquaduct-cli {CLI_VERSION}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        build_parser().print_help()
        return EXIT_ERROR
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        code = e.code
        if code is None:
            return EXIT_OK
        return int(code) if isinstance(code, int) else EXIT_ERROR

    cmd = getattr(args, "command", None)
    try:
        if cmd == "run":
            return cmd_run(args)
        if cmd == "preflight":
            return cmd_preflight()
        if cmd == "config":
            cc = getattr(args, "config_cmd", None)
            if cc == "show":
                return cmd_config_show(args)
            if cc == "path":
                return cmd_config_path()
            if cc == "validate":
                return cmd_config_validate(args)
        if cmd == "models":
            mc = getattr(args, "models_cmd", None)
            if mc == "list":
                return cmd_models_list()
            if mc == "download":
                return cmd_models_download(args)
        if cmd == "tasks":
            tc = getattr(args, "tasks_cmd", None)
            if tc == "list":
                return cmd_tasks_list()
        if cmd == "version":
            return cmd_version()
    except Exception as e:
        print(f"{e}", file=sys.stderr)
        return EXIT_INTERNAL

    print("Unknown command", file=sys.stderr)
    return EXIT_ERROR
