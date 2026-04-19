# Headless CLI

Aquaduct can run **without the desktop UI** using subcommands. Settings are the same object as the app: **`ui_settings.json`** under **`.Aquaduct_data/`** next to your install (see [`app_dirs`](../src/core/app_dirs.py)).

## Entry

```powershell
python main.py <command> [options]
```

Legacy flags still work:

- `python main.py` — desktop UI (default).
- `python main.py --cli --once` — one headless run using saved settings.
- `python main.py --cli` — watch loop (interval via `--interval-hours`); each iteration reloads **`ui_settings.json`** and applies the Hugging Face token the same way as `--once`.

Print top-level help:

```powershell
python main.py help
```

## Subcommands

### `version`

Prints the CLI bundle version string.

### `config path`

Prints the absolute path to `ui_settings.json`.

### `config show`

Dumps effective settings as one JSON object (stdout). Options:

- `--pretty` — indented JSON.
- `--no-secrets` — redacts tokens and API keys (safe for logs).

### `config validate`

Loads and parses `ui_settings.json`. With `--preflight`, also runs [`preflight_check`](../src/runtime/preflight.py) (exit code **1** on failure).

### `preflight`

Runs strict preflight only (no generation). Exit **1** if not OK.

### `run`

- **`--once`** — single pipeline run; prints the output video folder path (or “No new items found.”).
- **`--watch`** — repeat forever; **`--interval-hours`** (default `4`) controls sleep between runs. Each iteration reloads settings from disk.
- **`--merge-json PATH`** — deep-merge a partial JSON object into loaded settings before the run (same top-level keys as `ui_settings.json`, e.g. `video`, `video_format`).
- **`--music PATH`** — override `background_music_path` for that run.
- **`--dry-run`** — preflight only, no generation.

Progress messages go to **stderr**; the final path for `--once` goes to **stdout** for scripting.

### `models list`

Lists curated Hugging Face repos (script / image / video / voice) and whether a local snapshot exists under the **resolved models directory** (same rule as the app: **default** `.Aquaduct_data/models`, or **external** path from `ui_settings.json` when configured — see [Config](config.md) / `models_dir_for_app` in [`src/core/models_dir.py`](../src/core/models_dir.py)).

### `models download`

Downloads snapshots into that same **resolved** models folder (not always `.Aquaduct_data/models/` if **External** storage is saved).

- `--role script|image|video|voice|all` (default: `all`).
- `--repo-id ORG/NAME` — download only this id (must appear in the curated list).

Requires a Hugging Face token for gated models: set **`HF_TOKEN`** or **`HUGGINGFACEHUB_API_TOKEN`**, or save a token in the UI (applied to the environment when present).

### `tasks list`

Read-only list of render/upload tasks (same data as the **Tasks** tab).

## Environment variables (cloud)

Prefer env for secrets so containers do not store keys in JSON:

| Variable | Role |
|----------|------|
| `HF_TOKEN` / `HUGGINGFACEHUB_API_TOKEN` | Hugging Face downloads / gated models |
| `OPENAI_API_KEY` | API mode / OpenAI routing (see [`model_backend`](../src/runtime/model_backend.py)) |
| `REPLICATE_API_TOKEN` | API mode / Replicate |
| `AQUADUCT_DEBUG` | Debug categories (comma-separated); same as UI |

## Docker-style example

Mount a persistent data directory at the repo root so `.Aquaduct_data` is stable:

```bash
docker run --rm -v /host/aquaduct_data:/app/.Aquaduct_data -e HF_TOKEN=hf_xxx aquaduct-image \
  python main.py run --once
```

Adjust image name and working directory to match your Dockerfile.

## Limitations

- **TikTok / YouTube OAuth** flows are browser-based in the UI; the CLI does not perform OAuth. Use **`tasks list`** or filesystem paths to **`final.mp4`** for external upload tools.
- **Storyboard preview / approve** is interactive; automation would require future flags (e.g. prebuilt JSON).
- **`models download`** uses the same curated list as the Model tab; ad-hoc Hub ids are not validated except via `--repo-id` whitelist.

## See also

- [`main.md`](main.md) — orchestrator and legacy `--cli` flags.
- [`hardware.md`](hardware.md) — VRAM / fit hints for local models.
