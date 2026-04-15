from __future__ import annotations

from src.personalities import get_personality_by_id, get_personality_presets


def test_personality_ids_unique():
    presets = get_personality_presets()
    ids = [p.id for p in presets]
    assert len(ids) == len(set(ids))


def test_get_personality_by_id_fallback():
    p = get_personality_by_id("does-not-exist")
    assert p is not None
    assert p.id in {pp.id for pp in get_personality_presets()}

