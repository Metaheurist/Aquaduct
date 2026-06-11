# Topics tab — tags, Discover, grounding notes

## Purpose

The **Topics** tab edits `topic_tags_by_mode`: one tag list per **video format** (News, Cartoon, Explainer, Unhinged, Creepypasta, Health advice, NSFW — same buckets as Run). Tags drive crawls, Discover seeds, and the script LLM.

## Tags (chip flow)

- **Mode** dropdown: choose which format’s list you are editing ([`UI/tabs/topics_tab.py`](../../UI/tabs/topics_tab.py)).
- Tags render as **removable chips** in a capped scroll area (~160px) using [`FlowLayout`](../../UI/widgets/flow_layout.py) and [`TopicChip`](../../UI/widgets/topic_chip.py).
- **Add tag** appends to the current mode list; click a chip to select it; use the chip **remove** control or bulk actions to clear tags.

## Selected-tag notes (grounding)

- One optional note field targets the **currently selected chip** only (replaces the old per-tag notes block).
- Persisted as `topic_tag_notes` in `ui_settings.json` (keys: tag text **normalized** to lowercase, single-line notes **≤ 240 chars** after sanitisation — [`sanitize_topic_tag_notes`](../../src/content/topic_constraints.py)).
- At run time, `main.py` merges these into [`topic_constraints_block`](../../src/content/topic_constraints.py) alongside active tags (`effective_topic_tags`).

## Discover

- **News / Explainer**: headline-style suggestions. At pipeline time, headline pick among top-ranked items uses **weighted random** selection ([`pick_weighted_item`](../../src/content/crawler.py)) so runs vary without ignoring relevance.
- **Cartoon, Unhinged, Creepypasta, Health advice, NSFW**: Firecrawl web seeds (requires API tab key). Research packs under `data/topic_research/<mode>/` when enabled. For **NSFW**, Discover applies denylist filtering on suggested lines unless a **session guardrail bypass** is active ([Desktop UI](ui.md), [Config](../reference/config.md#session-guardrail-bypass)).

See [Desktop UI overview](ui.md) and [Crawler](../integrations/crawler.md).

## Suggest with LLM

**Suggest with LLM** batches missing grounding lines via the **Script (LLM)** model (local or API). Progress uses **`AuxiliaryProgressDialog`** chrome as Characters / field expand ([`UI/dialogs/auxiliary_progress_dialog.py`](../../UI/dialogs/auxiliary_progress_dialog.py)).

## Related pipeline docs

- [Brain — topic tags & hard constraints](../pipeline/brain.md#topic-tags--hard-constraints)
- [Prompt context fusion](../pipeline/prompt-context.md)
- [Config — `topic_tag_notes`](../reference/config.md#app-settings-ui--pipeline)
- [Shared UI widgets](shared-widgets.md)
