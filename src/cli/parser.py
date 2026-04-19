"""Argparse tree for Aquaduct CLI subcommands."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python main.py",
        description="Aquaduct headless CLI — same settings as the desktop app (ui_settings.json).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # run
    run = sub.add_parser("run", help="Run the video pipeline (local or API per settings).")
    run_mode = run.add_mutually_exclusive_group(required=True)
    run_mode.add_argument("--once", action="store_true", help="Single generation cycle and exit.")
    run_mode.add_argument("--watch", action="store_true", help="Repeat forever with --interval-hours.")
    run.add_argument(
        "--interval-hours",
        type=float,
        default=4.0,
        help="Hours between runs when using --watch (default: 4).",
    )
    run.add_argument(
        "--merge-json",
        type=str,
        default="",
        metavar="PATH",
        help="Merge a partial JSON object into settings before run (same keys as ui_settings.json).",
    )
    run.add_argument(
        "--music",
        type=str,
        default="",
        metavar="PATH",
        help="Override background music path for this run.",
    )
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="Run preflight only; do not generate.",
    )

    # preflight
    sub.add_parser("preflight", help="Validate environment and settings (strict).")

    # config
    cfg = sub.add_parser("config", help="Inspect ui_settings.json.")
    cfg_sub = cfg.add_subparsers(dest="config_cmd", required=True)
    show = cfg_sub.add_parser("show", help="Print settings as JSON.")
    show.add_argument("--pretty", action="store_true", help="Indented output.")
    show.add_argument(
        "--no-secrets",
        action="store_true",
        help="Redact tokens and API keys (for logs).",
    )
    cfg_sub.add_parser("path", help="Print absolute path to ui_settings.json.")
    val = cfg_sub.add_parser("validate", help="Load settings; optional preflight.")
    val.add_argument(
        "--preflight",
        action="store_true",
        help="Also run preflight_check (exit 1 on failure).",
    )

    # models
    m = sub.add_parser("models", help="Curated Hugging Face models under models/.")
    m_sub = m.add_subparsers(dest="models_cmd", required=True)
    m_sub.add_parser("list", help="List curated models and local snapshot status.")
    dl = m_sub.add_parser("download", help="Download snapshot(s) into models/.")
    dl.add_argument(
        "--role",
        choices=("script", "image", "video", "voice", "all"),
        default="all",
        help="Which dropdown group to download (default: all).",
    )
    dl.add_argument(
        "--repo-id",
        type=str,
        default="",
        metavar="ORG/NAME",
        help="Download only this repo id (must appear in curated list).",
    )

    # tasks (read-only; same data as Tasks tab)
    tsk = sub.add_parser("tasks", help="Render / upload queue (read-only).")
    tsk_sub = tsk.add_subparsers(dest="tasks_cmd", required=True)
    tsk_sub.add_parser("list", help="List tasks from upload_tasks.json.")

    sub.add_parser("version", help="Print CLI version string.")

    return p
