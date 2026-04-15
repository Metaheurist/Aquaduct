# Changelog

All notable changes to this project will be documented in this file.

## Unreleased
- Added PyQt6 desktop UI (`UI/` package; launcher `UI/ui_app.py`) with TikTok-style theme and tabbed controls.
- Added Settings tab: dependency check/install and model select/download.
- Added My PC tab: hardware detection + model fit markers.
- Added settings persistence via `ui_settings.json`.
- Added model overrides in `AppSettings` (script/video/voice).
- Updated build script to build UI exe (`build/build.ps1 -UI`).
- Added Branding tab: optional palette-driven theme overrides (presets + custom hex + color picker).
- Added optional logo watermark overlay for generated videos (configured in Branding tab).
- Improved model downloads: cancelable UI downloads and resumable downloads when re-run.

## 0.1.0 — 2026-04-15
- Initial MVP scaffold: crawler → local script generation → local TTS + captions → SDXL Turbo images → micro-clip editor → per-video outputs under `videos/`.

