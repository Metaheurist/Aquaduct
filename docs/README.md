# Aquaduct documentation

| Folder | Contents |
|--------|----------|
| [reference](reference/) | Config, CLI, [model + tier + VRAM inventory](reference/model_inventory.md), models, hardware (incl. multi-GPU VRAM-first notes), VRAM, [quantization](reference/quantization.md), [inference profiles](reference/inference_profiles.md) |
| [pipeline](pipeline/) | Main loop, brain ([LLM chat RAG env](reference/config.md#title-bar-llm-chat--rag-and-optional-tuning)), artist, voice, editor, FFmpeg, performance, [**crash resilience** (checkpoints / resume / heartbeat)](pipeline/crash-resilience.md) |
| [ui](ui/) | Desktop UI ([overview](ui/ui.md), [shared widgets](ui/shared-widgets.md), branding, characters, [Topics](ui/topics.md), [Video tab v2](ui/video-tab-v2.md)); title-bar shortcuts include **F12** session guardrail bypass — [config](reference/config.md#session-guardrail-bypass) |
| [integrations](integrations/) | API mode (Gemini, SiliconFlow, Magic Hour, Inworld, OpenAI, Replicate, …), crawler, ElevenLabs, TikTok, YouTube |
| [review](review/) | QA / review checklists (e.g. [API mode](review/api_mode_checklist.md)) |
| [build](build/) | Windows EXE build, model + YouTube demos |
| [tests/](../tests/) (repo root) | Pytest tree: [`tests/README.md`](../tests/README.md) describes `tests/<area>/` subfolders (`cli`, `ui`, `models`, …) |
| [`debug/`](../debug/) | Categorized stderr debug (`dprint`), `MODULE_DEBUG_FLAGS`, env `AQUADUCT_DEBUG`, index at [`debug/README.md`](../debug/README.md) |

Start from the project [README.md](../README.md) for a full map of links.
