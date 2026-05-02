# Topics tab — tags, Discover, grounding notes

## Purpose

The **Topics** tab edits `topic_tags_by_mode`: one tag list per **video format** (News, Cartoon, Explainer, Unhinged, Creepypasta, Health advice — same buckets as Run). Tags drive crawls, Discover seeds, and the script LLM.

## Tags

- **Mode** dropdown: choose which format’s list you are editing (`UI/tabs/topics_tab.py`).
- **Add tag** appends to the current mode list; selections can be removed or cleared.

## Discover

- **News / Explainer**: headline-style suggestions.
- **Cartoon, Unhinged, Creepypasta, Health advice**: Firecrawl web seeds (requires API tab key). Research packs under `data/topic_research/<mode>/` when enabled.

See [Desktop UI overview](ui.md) and [Crawler](../integrations/crawler.md).

## Per-tag grounding notes (hard constraints layer)

Below the tag list, **Per-tag notes (grounding)** shows one optional line per tag for the **currently selected Topics mode**.

- Persisted as `topic_tag_notes` in `ui_settings.json` (keys: tag text **normalized** to lowercase, single-line notes **≤ 240 chars** after sanitisation — [`sanitize_topic_tag_notes`](../../src/content/topic_constraints.py)).
- At run time, `main.py` merges these into [`topic_constraints_block`](../../src/content/topic_constraints.py) alongside active tags (`effective_topic_tags`) so the script model sees tags as **hard** constraints plus your short cue per tag.
- Tags are global by **string**: the same wording in two formats shares one note unless you rename one tag.

## Related pipeline docs

- [Brain — topic tags & hard constraints](../pipeline/brain.md#topic-tags--hard-constraints)
- [Prompt context fusion](../pipeline/prompt-context.md)
- [Config — `topic_tag_notes`](../reference/config.md#app-settings-ui--pipeline)
