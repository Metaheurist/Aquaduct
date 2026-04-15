# Models + downloads

## Where models are used
- **Script model (LLM)**: `src/brain.py` (local inference; 4-bit target when supported)
- **Video/images model**: `src/artist.py` (diffusers text-to-image, SDXL Turbo default)
- **Voice model (TTS)**: `src/voice.py` (Kokoro target; offline fallback)

## UI model selection
In the UI **Settings** tab you can pick and download models separately for:
- Script
- Video/images
- Voice

Each option is labeled with a relative speed marker:
- `fastest` / `faster` / `slow`

## How downloads work
Downloads use Hugging Face Hub snapshot download into:
- `.cache/hf/`

This is implemented in:
- `src/model_manager.py`

## Model overrides
Selected model repo IDs are persisted in `ui_settings.json` and passed into the pipeline through:
- `AppSettings.llm_model_id`
- `AppSettings.image_model_id`
- `AppSettings.voice_model_id`

If an override is blank, the pipeline falls back to `src/config.py:get_models()`.

## Tokens / gated models
Most public repos download without a token.

If a repo is **gated** (common for some Llama checkpoints), you’ll need a Hugging Face access token via `HF_TOKEN` / login.

