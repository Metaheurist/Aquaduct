# Video series mode

Multi-episode **video** runs share a frozen settings snapshot and a rolling **series bible** so each episode can continue the prior script. Episodes are **separate pipeline jobs** executed one after another through the Run queue.

## UI (Run tab)

Enable **Generate as multi-episode series** inside **Video series (continuation)** when **media mode** is **Video**. Set **Episodes to generate** (1–50) in that same group — it is the only episode count control while series mode is on (the **Output** quantity row is hidden so the value is not duplicated). When series mode is off, **Videos to generate** under **Output** queues that many independent single-video runs.

Options:

- **Series name** — optional; used for the folder name under `videos/`.
- **Source per episode** — **Auto** (news / health_advice → fresh headline per episode; other formats and custom brief → lock to episode 1 sources), **Lock episode 1 sources**, or **Fresh source each episode**.
- **Lock art style, models & characters** — when on (default), later episodes use the snapshot only for art style, pipelines models, branding, character, and personality. When off, live UI choices for those fields apply on top of the snapshot (tokens/API keys still come from live settings).
- **Carry recap / series bible** — when on, the script LLM gets the previous episode digest and full bible text.
- **Continue series if an episode fails** — when off (default), a failed episode removes remaining queued episodes **with the same series slug**. When on, the queue keeps going; the recap chain still follows the **last successful** registered episode.

## On disk

For slug `my_show`:

- `videos/my_show/series.json` — frozen `settings_snapshot`, optional `locked_sources` / `locked_article_excerpt` for **lock** strategy, episode index.
- `videos/my_show/series_bible.md` — markdown sections `### Episode N: title` plus recap text.
- `videos/my_show/episode_NNN_slugtitle/` — per-episode project (`final.mp4`, `meta.json`, `script.txt`, …). `meta.json` includes a `series` object with `slug`, `episode_index`, `episode_total`, `previous_episode_dir`.

Each run also writes `runs/<run_id>/assets/series_context.json` when `series_context` is present.

## Script LLM

`generate_script` / `generate_script_openai` append **Previous episode recap** and **Series bible** blocks when non-empty, plus substance rules telling the model to continue the arc without rehashing.

## Recap generation

After a successful video export, `register_episode` stores metadata and appends to the bible. Recap text prefers a short LLM summary (API or local); on failure or tight setups, **`src/series/recap.py`** falls back to first/last sentences of the script.

## Library tab

`scan_finished_videos` treats folders with `series.json` as series roots and lists each `episode_*` child that contains `final.mp4`, with titles like `Series: <name> · Ep N — <episode title>`.

## Cancel

Canceling the pipeline clears the whole queue (existing behavior). The log notes how many dropped jobs were **series episodes**.

## Tests

- `tests/content/test_brain_series_blocks.py` — prompt continuity blocks.
- `tests/series/test_recap_and_layout.py` — layout + library scan + fallback recap.
- `tests/series/test_store.py`, `tests/series/test_rehydrate.py` — persistence and style merge.
- `tests/ui/test_series_failure_abort.py` — queue pruning helper used on failure.
- `tests/ui/test_series_queue.py` — Run queue behavior for series batches.
- `tests/settings/test_series_settings_roundtrip.py` — series fields round-trip in settings.
