# Aquaduct documentation

| Folder | Contents |
|--------|----------|
| [reference](reference/) | Config, CLI, [model + tier + VRAM inventory](reference/model_inventory.md), models, hardware (incl. multi-GPU VRAM-first notes), VRAM, [quantization](reference/quantization.md), [inference profiles](reference/inference_profiles.md) |
| [pipeline](pipeline/) | Main loop, brain ([LLM chat RAG env](reference/config.md#title-bar-llm-chat--rag-and-optional-tuning)), artist, voice ([caption alignment](pipeline/voice.md)), editor, FFmpeg, [performance](pipeline/performance.md), [**crash resilience** (checkpoints / resume / `run_report.json` / queue persistence)](pipeline/crash-resilience.md), [series mode](pipeline/series-mode.md) |
| [ui](ui/) | Desktop UI ([overview](ui/ui.md), [shared widgets](ui/shared-widgets.md), **Basic \| Advanced** per-tab mode, Visual Basic tiles/step cards, branding, characters, [Topics](ui/topics.md), [Video tab v2](ui/video-tab-v2.md)); Library search + series resume; **F12** guardrail bypass (requires env at launch) — [config](reference/config.md#session-guardrail-bypass) |
| [integrations](integrations/) | API mode (Gemini, SiliconFlow, Magic Hour, Inworld, OpenAI, Replicate, …), crawler, ElevenLabs, TikTok, YouTube |
| [review](review/) | QA / review checklists (e.g. [API mode](review/api_mode_checklist.md)) |
| [build](build/) | Windows EXE build, model + YouTube demos |
| [tests/](../tests/) (repo root) | Pytest tree: [`tests/README.md`](../tests/README.md) describes `tests/<area>/` subfolders (`cli`, `ui`, `models`, …) |
| [`debug/`](../debug/) | Categorized stderr debug (`dprint`), `MODULE_DEBUG_FLAGS`, env `AQUADUCT_DEBUG`, index at [`debug/README.md`](../debug/README.md) |

Start from the project [README.md](../README.md) for install and a full map of links. Use the table above to jump into a specific area.
