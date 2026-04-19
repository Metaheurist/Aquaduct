from __future__ import annotations

import json

import pytest

from src.content.crawler import NewsItem


def test_image_url_from_firecrawl_row_metadata() -> None:
    from src.content.firecrawl_news import image_url_from_firecrawl_row

    assert (
        image_url_from_firecrawl_row({"metadata": {"ogImage": "https://cdn.example/a.jpg"}})
        == "https://cdn.example/a.jpg"
    )
    assert image_url_from_firecrawl_row({"image": "https://x.example/b.png"}) == "https://x.example/b.png"


def test_topic_research_digest_for_script_reads_manifest(tmp_path) -> None:
    from src.content.topic_research_assets import topic_research_digest_for_script

    root = tmp_path / "topic_research" / "unhinged"
    root.mkdir(parents=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "title": "a meme title",
                        "url": "https://example.com/x",
                        "local_image": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    s = topic_research_digest_for_script(tmp_path, "unhinged")
    assert "a meme title" in s
    assert "https://example.com/x" in s


def test_write_topic_research_pack_writes_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from src.content import topic_research_assets as tra

    monkeypatch.setattr(tra, "try_fetch_og_image_url", lambda *_a, **_k: None)
    monkeypatch.setattr(tra, "_download_image", lambda *_a, **_k: None)

    from src.content.topic_research_assets import write_topic_research_pack

    items = [
        NewsItem(title="lowercase meme title here", url="https://example.com/p", source="Firecrawl"),
    ]
    root = write_topic_research_pack(items=items, mode="unhinged", data_dir=tmp_path)
    assert root is not None
    man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert man["mode"] == "unhinged"
    assert len(man["entries"]) == 1
    assert man["entries"][0]["title"] == "lowercase meme title here"
