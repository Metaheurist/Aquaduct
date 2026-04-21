"""Title bar / dialog outline buttons (antialiased chrome)."""

from __future__ import annotations

import pytest


@pytest.mark.qt
def test_styled_outline_button_fixed_and_min_sizes(qapplication):
    from UI.title_bar_outline_button import TitleBarOutlineButton, styled_outline_button

    close = styled_outline_button("✕", "danger", fixed=(44, 32))
    assert isinstance(close, TitleBarOutlineButton)
    assert close.minimumWidth() == 44 == close.maximumWidth()
    assert close.minimumHeight() == 32 == close.maximumHeight()

    ok = styled_outline_button("OK", "accent_icon", min_width=100, min_height=34)
    assert ok.minimumWidth() == 100
    assert ok.minimumHeight() == 34


@pytest.mark.qt
def test_title_bar_outline_button_chrome_property(qapplication):
    from UI.title_bar_outline_button import TitleBarOutlineButton

    b = TitleBarOutlineButton("x", variant="muted_icon")
    assert b.property("chrome") == "title_outline"


@pytest.mark.qt
def test_frameless_dialog_close_is_outline_button(qapplication):
    from UI.frameless_dialog import FramelessDialog
    from UI.title_bar_outline_button import TitleBarOutlineButton

    d = FramelessDialog(None, title="Test")
    close = getattr(d, "_frameless_close_button", None)
    assert isinstance(close, TitleBarOutlineButton)
    assert close.text() == "✕"


@pytest.mark.qt
def test_tutorial_dialog_nav_buttons_are_outline(qapplication):
    from UI.title_bar_outline_button import TitleBarOutlineButton
    from UI.tutorial_dialog import TutorialDialog

    dlg = TutorialDialog(None)
    assert isinstance(dlg._prev_btn, TitleBarOutlineButton)
    assert isinstance(dlg._next_btn, TitleBarOutlineButton)
