# Test layout

Run the suite from the repository root; `pytest` collects everything under this directory.

| Subfolder | What lives here |
|-----------|-----------------|
| [`cli/`](cli/) | Headless CLI parser, config merge, `ui_settings` roundtrips |
| [`ui/`](ui/) | PyQt6 / `pytest-qt` desktop UI (`@pytest.mark.qt` where applicable) |
| [`models/`](models/) | Local HF model manager, VRAM / CUDA policy, diffusion presets, `torch` dtypes, inference profiles |
| [`platform/`](platform/) | Remote API clients (OpenAI-shaped, Kling, Replicate, ElevenLabs, …) |
| [`runtime/`](runtime/) | `api_generation`, preflight, pipeline control, import smoke, run-queue contract |
| [`content/`](content/) | Brain, story pipeline, characters, personalities, story context; LLM chat RAG (**`llm_chat_rag`**, **`llm_chat_system_prompt`**); pipeline generation / EOS routing (**`test_chat_generation`**) |
| [`render/`](render/) | Artist / clips / FFmpeg / pro-mode / video format helpers |
| [`discover/`](discover/) | Topic discovery, Firecrawl / crawler, news-cache modes |
| [`social/`](social/) | Upload tasks, TikTok/TikTok-style posting helpers |
| [`core/`](core/) | App paths, media library FS |
| [`debug/`](debug/) | `dprint` category registry, `MODULE_DEBUG_FLAGS` / `AQUADUCT_DEBUG` merge, `active_categories` cache |
| [`gpu/`](gpu/) | Multi-GPU sharding registry / gates ([`src/gpu/multi_device/`](../src/gpu/multi_device/)) |

Shared fixtures: [`conftest.py`](conftest.py).

```powershell
# Typical headless run (no Qt)
pytest -q -m "not qt"

# API-mode smoke (example)
pytest tests/models/test_model_backend.py tests/runtime/test_preflight.py tests/runtime/test_api_generation.py tests/runtime/test_api_model_catalog.py tests/platform/test_kling_client.py tests/platform/test_openai_client.py -q
```

See also **Tests** in the project [`README.md`](../README.md) and **Test tiers** in [`DEPENDENCIES.md`](../DEPENDENCIES.md).
