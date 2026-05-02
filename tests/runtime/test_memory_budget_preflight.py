from __future__ import annotations


def test_analyze_video_catastrophic_shortfall_blocks(monkeypatch):
    import src.runtime.memory_budget_preflight as mb

    monkeypatch.setenv("AQUADUCT_MEMORY_PREFLIGHT", "1")
    monkeypatch.delenv("AQUADUCT_MEMORY_PREFLIGHT_FAIL", raising=False)
    monkeypatch.setenv("AQUADUCT_HOST_RAM_PREFLIGHT_FACTOR", "2.0")
    monkeypatch.setenv("AQUADUCT_MEMORY_SEVERE_SHORTFALL_FRAC", "0.35")

    class _VM:
        available = int(21 * 1024**3)
        percent = 72.0

    monkeypatch.setattr("psutil.virtual_memory", lambda: _VM())
    monkeypatch.setattr(mb, "hf_cache_size_estimate_gib", lambda *args, **kwargs: 117.5)

    w, b = mb.analyze_stage_memory_budget(
        stage_label="Video load",
        role="video",
        repo_id="Wan-AI/test",
        settings=None,
    )
    assert w and "low host RAM" in w
    assert b and "refusing run" in (b or "")


def test_empty_fail_roles_disables_fatal_gate(monkeypatch):
    import src.runtime.memory_budget_preflight as mb

    monkeypatch.setenv("AQUADUCT_MEMORY_PREFLIGHT", "1")
    monkeypatch.setenv("AQUADUCT_MEMORY_PREFLIGHT_FAIL_ROLES", "")
    monkeypatch.delenv("AQUADUCT_MEMORY_PREFLIGHT_FAIL", raising=False)

    class _VM:
        available = int(21 * 1024**3)
        percent = 72.0

    monkeypatch.setattr("psutil.virtual_memory", lambda: _VM())
    monkeypatch.setattr(mb, "hf_cache_size_estimate_gib", lambda *args, **kwargs: 117.5)

    w, b = mb.analyze_stage_memory_budget(
        stage_label="Video load",
        role="video",
        repo_id="Wan-AI/test",
        settings=None,
    )
    assert w
    assert b is None


def test_preflight_fail_env_makes_every_warn_fatal(monkeypatch):
    import src.runtime.memory_budget_preflight as mb

    monkeypatch.setenv("AQUADUCT_MEMORY_PREFLIGHT", "1")
    monkeypatch.setenv("AQUADUCT_MEMORY_PREFLIGHT_FAIL", "1")

    class _VM:
        available = int(21 * 1024**3)
        percent = 72.0

    monkeypatch.setattr("psutil.virtual_memory", lambda: _VM())
    monkeypatch.setattr(mb, "hf_cache_size_estimate_gib", lambda *args, **kwargs: 117.5)

    w, b = mb.analyze_stage_memory_budget(
        stage_label="Video load",
        role="video",
        repo_id="Wan-AI/test",
        settings=None,
    )
    assert w == b

