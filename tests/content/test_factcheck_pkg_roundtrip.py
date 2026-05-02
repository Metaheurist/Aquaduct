from __future__ import annotations

from src.content.brain import ScriptSegment, VideoPackage
from src.content.factcheck import _from_payload, _to_payload


def test_video_package_payload_roundtrip() -> None:
    pkg = VideoPackage(
        title="Test",
        description="Desc",
        hashtags=["#one"],
        hook="hook",
        segments=[ScriptSegment(narration="Say this", visual_prompt="A cat", on_screen_text="Hi")],
        cta="cta",
    )
    d = _to_payload(pkg)
    pkg2 = _from_payload(d)
    assert pkg2.title == "Test"
    assert len(pkg2.segments or []) == 1
