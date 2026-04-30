from __future__ import annotations

from UI.help.tutorial_links import help_tooltip_rich


def test_help_tooltip_rich_emits_html_and_topic_url() -> None:
    html = help_tooltip_rich("Hello & world.\nLine two.", "welcome", slide=2)
    assert html.strip().lower().startswith("<html")
    assert "topic://welcome?slide=2" in html
    assert "Hello &amp; world." in html


def test_help_tooltip_rich_default_slide_zero() -> None:
    html = help_tooltip_rich("x", "run", slide=None)
    assert "topic://run?slide=0" in html
