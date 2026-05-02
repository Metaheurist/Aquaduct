from __future__ import annotations

import time

from src.runtime import load_heartbeat as lb


def test_load_heartbeat_footer_records_notice() -> None:
    lb.set_load_heartbeat_notice("Still loading test…")
    assert lb.get_load_heartbeat_footer_text(max_age_s=5.0) != ""
    time.sleep(0.05)
    assert "Still loading" in lb.get_load_heartbeat_footer_text(max_age_s=5.0)
