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


def test_script_host_ram_warn_blocks_by_default(monkeypatch):
    """Marginal free RAM vs LLM heuristic should refuse the run (Windows OOM-kill without traceback)."""
    import dataclasses

    from src.core.config import AppSettings
    import src.runtime.memory_budget_preflight as mb

    monkeypatch.setenv("AQUADUCT_MEMORY_PREFLIGHT", "1")
    monkeypatch.delenv("AQUADUCT_MEMORY_PREFLIGHT_FAIL", raising=False)
    monkeypatch.setenv("AQUADUCT_HOST_RAM_PREFLIGHT_FACTOR", "2.0")
    monkeypatch.setenv("AQUADUCT_MEMORY_SEVERE_SHORTFALL_FRAC", "0.35")

    class _VM:
        available = int(23 * 1024**3)

    monkeypatch.setattr("psutil.virtual_memory", lambda: _VM())
    monkeypatch.setattr(mb, "hf_cache_size_estimate_gib", lambda *args, **kwargs: 20.0)
    s = dataclasses.replace(AppSettings(), script_quant_mode="int8")
    w, b = mb.analyze_stage_memory_budget(
        stage_label="Script load",
        role="script",
        repo_id="Foo/Bar",
        settings=s,
    )
    assert w and "low host RAM" in w
    assert b and "refusing run" in (b or "") and "host RAM shortfall" in (b or "")


def test_error_on_warn_roles_empty_allows_marginal_script(monkeypatch):
    import dataclasses

    from src.core.config import AppSettings
    import src.runtime.memory_budget_preflight as mb

    monkeypatch.setenv("AQUADUCT_MEMORY_PREFLIGHT", "1")
    monkeypatch.setenv("AQUADUCT_MEMORY_PREFLIGHT_ERROR_ON_WARN_ROLES", "")
    monkeypatch.delenv("AQUADUCT_MEMORY_PREFLIGHT_FAIL", raising=False)
    monkeypatch.setenv("AQUADUCT_HOST_RAM_PREFLIGHT_FACTOR", "2.0")

    class _VM:
        available = int(23 * 1024**3)

    monkeypatch.setattr("psutil.virtual_memory", lambda: _VM())
    monkeypatch.setattr(mb, "hf_cache_size_estimate_gib", lambda *args, **kwargs: 20.0)
    s = dataclasses.replace(AppSettings(), script_quant_mode="int8")
    w, b = mb.analyze_stage_memory_budget(
        stage_label="Script load",
        role="script",
        repo_id="Foo/Bar",
        settings=s,
    )
    assert w
    assert b is None


def test_hub_snapshot_scaled_for_script_int8(monkeypatch):
    import dataclasses

    from src.core.config import AppSettings
    import src.runtime.memory_budget_preflight as mb

    monkeypatch.setenv("AQUADUCT_MEMORY_PREFLIGHT", "1")
    monkeypatch.setenv("AQUADUCT_MEMORY_PREFLIGHT_ERROR_ON_WARN_ROLES", "")
    monkeypatch.setenv("AQUADUCT_HOST_RAM_PREFLIGHT_FACTOR", "2.0")

    class _VM:
        available = int(20 * 1024**3)

    monkeypatch.setattr("psutil.virtual_memory", lambda: _VM())
    monkeypatch.setattr(mb, "hf_cache_size_estimate_gib", lambda *args, **kwargs: 20.0)
    s = dataclasses.replace(AppSettings(), script_quant_mode="int8")
    w, b = mb.analyze_stage_memory_budget(
        stage_label="Script load",
        role="script",
        repo_id="Foo/Bar",
        settings=s,
    )
    assert w and "~12.4" in w and "INT8" in w
    assert b is None

