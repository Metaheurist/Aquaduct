# Test layout

Run the suite from the repository root so `pytest.ini` applies; `pytest` then collects everything under this directory.

| Subfolder | What lives here |
|-----------|-----------------|
| [`cli/`](cli/) | Headless CLI parser, config merge, `ui_settings` roundtrips |
| [`settings/`](settings/) | Settings persistence; [`test_advanced_tabs_roundtrip.py`](settings/test_advanced_tabs_roundtrip.py) for per-tab Basic/Advanced mode |
| [`ui/`](ui/) | PyQt6 / `pytest-qt` desktop UI (`@pytest.mark.qt` where applicable); F4 image playground ([`test_image_playground_dialog.py`](test_image_playground_dialog.py)); NSFW Run tab / session bypass ([`test_run_tab_nsfw_combo.py`](test_run_tab_nsfw_combo.py)); pipeline series queue ([`test_pipeline_series_queue.py`](ui/test_pipeline_series_queue.py)); **Visual Basic Mode** ([`test_visual_primitives.py`](ui/test_visual_primitives.py), [`test_themed_switch.py`](ui/test_themed_switch.py), [`test_basic_advanced_mode.py`](ui/test_basic_advanced_mode.py), [`test_optional_basic_advanced_tabs.py`](ui/test_optional_basic_advanced_tabs.py)); **UI modernization** widgets/tabs/preflight ([`test_ui_modernization_widgets.py`](test_ui_modernization_widgets.py), [`test_ui_modernization_tabs.py`](test_ui_modernization_tabs.py), [`test_ui_preflight_install_prompt.py`](test_ui_preflight_install_prompt.py)) |
| [`models/`](models/) | Local HF model manager, VRAM / CUDA policy, diffusion presets, `torch` dtypes, inference profiles |
| [`platform/`](platform/) | Remote API clients (OpenAI-shaped, Kling, Replicate, ElevenLabs, …) |
| [`runtime/`](runtime/) | `api_generation`, preflight, pipeline control, import smoke, run-queue contract; NSFW preflight + **`AQUADUCT_DEV_DISABLE_CONTENT_GUARDRAILS`** ([`test_preflight_nsfw_uploads.py`](runtime/test_preflight_nsfw_uploads.py)); resume/checkpoint ([`test_run_once_resume.py`](runtime/test_run_once_resume.py)); SSRF guard ([`test_ssrf_guard.py`](runtime/test_ssrf_guard.py)); series queue ([`test_series_queue.py`](runtime/test_series_queue.py)) |
| [`content/`](content/) | Brain, story pipeline, characters, personalities, story context; LLM chat RAG (**`llm_chat_rag`**, **`llm_chat_system_prompt`**); pipeline generation / EOS routing (**`test_chat_generation`**); NSFW guardrails (**`test_nsfw_*`**, **`test_brain_api`**) |
| [`render/`](render/) | Artist / clips / FFmpeg / pro-mode / video format helpers; editor assembly ([`test_editor_assembly.py`](render/test_editor_assembly.py)) |
| [`discover/`](discover/) | Topic discovery, Firecrawl / crawler, news-cache modes |
| [`social/`](social/) | Upload tasks, TikTok/TikTok-style posting helpers |
| [`core/`](core/) | App paths, media library FS |
| [`debug/`](debug/) | `dprint` category registry, `MODULE_DEBUG_FLAGS` / `AQUADUCT_DEBUG` merge, `active_categories` cache |
| [`security/`](security/) | Secret fields encrypted in `ui_settings.json` and `pipeline_queue.json`, stripped from series snapshots, redacted in run reports and `config show` ([`test_secret_persistence.py`](security/test_secret_persistence.py)); tracked files free of credentials, local secrets gitignored ([`test_repo_hygiene.py`](security/test_repo_hygiene.py)); `write_ui_settings` redirects all app data ([`test_test_isolation.py`](security/test_test_isolation.py)); TikTok helpers refuse non-HTTPS URLs ([`test_outbound_urls.py`](security/test_outbound_urls.py)) |
| [`gpu/`](gpu/) | Multi-GPU sharding registry / gates ([`src/gpu/multi_device/`](../src/gpu/multi_device/)) |

Shared fixtures: [`conftest.py`](conftest.py).

- **`write_ui_settings`** / **`patch_paths`**: point every `application_data_dir` import (`app_dirs`, `config`, `ui_settings`, `pipeline_queue_store`, `secrets_crypto`, `llm_chat_rag`) at `tmp_path`. Tests must never touch the real `.Aquaduct_data`.
- **`built_main_window(settings=None)`**: constructs `MainWindow`, registers it with `qtbot`, and builds all deferred tabs so every tab widget exists.
- Qt tests stub the Hub size probe worker and the network reachability check; `pytest_configure` imports `torch` before Qt (on Windows, loading torch DLLs after `QApplication` can access-violate).
- `--timeout=300` (from **pytest-timeout**) is what CI uses; a hung Qt test fails instead of stalling the run.

```powershell
# Typical headless run (no Qt)
pytest -q -m "not qt"

# NSFW guardrails / session bypass (no Qt)
pytest tests/content/test_nsfw_prompt_branch.py tests/content/test_nsfw_topic_filter.py tests/runtime/test_preflight_nsfw_uploads.py -q

# Security tests
pytest tests/security -q

# Same command CI runs
pytest -m "not cuda_gpu" --timeout=300 -p no:cacheprovider

# API-mode smoke (example)
pytest tests/models/test_model_backend.py tests/runtime/test_preflight.py tests/runtime/test_api_generation.py tests/runtime/test_api_model_catalog.py tests/platform/test_kling_client.py tests/platform/test_openai_client.py -q
```

See also **Tests** in the project [`README.md`](../README.md) and **Test tiers** in [`DEPENDENCIES.md`](../DEPENDENCIES.md).
