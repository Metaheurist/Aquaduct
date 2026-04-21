# ElevenLabs (optional TTS)

Enable **ElevenLabs** on the **API** tab and paste your API key (or set the environment variable **`ELEVENLABS_API_KEY`**; the environment value takes precedence over the saved key).

## Behavior

- **Character Builder**: When ElevenLabs is enabled and a key is available, the **Characters** tab shows an **ElevenLabs voice** list (fetched from the ElevenLabs API). Pick a voice for a character only after turning off **Use project default voice** for that character; narration then uses ElevenLabs when you run the pipeline.
- **Offline / errors**: If the API is unreachable, quota is exceeded, or FFmpeg is missing, narration falls back to the existing local path (Kokoro when implemented, otherwise `pyttsx3`).
- **Network**: ElevenLabs TTS requires an internet connection for that step.

## Storage

- Key is stored in `ui_settings.json` (same as other API keys). Do not share that file or commit it if it contains secrets.

## API reference

See [ElevenLabs API documentation](https://elevenlabs.io/docs/api-reference/) for voice listing and text-to-speech endpoints.
