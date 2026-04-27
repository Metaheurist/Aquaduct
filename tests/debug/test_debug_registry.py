"""Tests for debug categories, MODULE_DEBUG_FLAGS merge, and dprint category registry."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _iter_py_under(*rel_parts: str) -> list[Path]:
    out: list[Path] = []
    for rel in rel_parts:
        base = _REPO_ROOT / rel
        if base.is_file():
            out.append(base)
        elif base.is_dir():
            out.extend(sorted(base.rglob("*.py")))
    return out


def _skip_path(p: Path) -> bool:
    rel = str(p.relative_to(_REPO_ROOT)).replace("\\", "/")
    if rel == "debug/debug_log.py":
        return True
    if rel == "debug/tools/smoke_categories.py":
        return True
    return False


class _DprintCatsVisitor(ast.NodeVisitor):
    """Collect first positional string literal for calls named ``dprint``."""

    def __init__(self) -> None:
        self.categories: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name_ok = isinstance(func, ast.Name) and func.id == "dprint"
        attr_ok = isinstance(func, ast.Attribute) and func.attr == "dprint"
        if name_ok or attr_ok:
            if node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                    self.categories.append(arg0.value)
        self.generic_visit(node)


def _dprint_categories_from_sources() -> set[str]:
    paths = _iter_py_under("src", "UI", "debug", "main.py")
    found: set[str] = set()
    for path in paths:
        if _skip_path(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        vis = _DprintCatsVisitor()
        vis.visit(tree)
        found.update(vis.categories)
    return found


def test_module_debug_flags_keys_match_registry() -> None:
    from debug.debug_log import DEBUG_CATEGORIES, MODULE_DEBUG_FLAGS

    assert set(MODULE_DEBUG_FLAGS.keys()) == set(DEBUG_CATEGORIES)
    assert all(v is False for v in MODULE_DEBUG_FLAGS.values())


def test_module_flag_enables_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import debug.debug_log as dl

    monkeypatch.delenv("AQUADUCT_DEBUG", raising=False)
    for c in dl.DEBUG_CATEGORIES:
        monkeypatch.delenv(f"AQUADUCT_DEBUG_{c.upper()}", raising=False)
    dl.apply_cli_debug("")
    try:
        dl.MODULE_DEBUG_FLAGS["pipeline"] = True
        dl.invalidate_debug_cache()
        assert "pipeline" in dl.active_categories()
        assert not dl.debug_enabled("brain")
    finally:
        dl.MODULE_DEBUG_FLAGS["pipeline"] = False
        dl.invalidate_debug_cache()


def test_env_all_enables_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    import debug.debug_log as dl

    monkeypatch.setenv("AQUADUCT_DEBUG", "all")
    dl.invalidate_debug_cache()
    assert dl.active_categories() == frozenset(dl.DEBUG_CATEGORIES)


def test_env_all_still_full_when_module_flags_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """``AQUADUCT_DEBUG=all`` enables everything; per-category file flags stay False."""
    import debug.debug_log as dl

    monkeypatch.setenv("AQUADUCT_DEBUG", "all")
    try:
        for c in dl.DEBUG_CATEGORIES:
            dl.MODULE_DEBUG_FLAGS[c] = False
        dl.invalidate_debug_cache()
        assert dl.active_categories() == frozenset(dl.DEBUG_CATEGORIES)
    finally:
        for c in dl.DEBUG_CATEGORIES:
            dl.MODULE_DEBUG_FLAGS[c] = False
        dl.invalidate_debug_cache()


def test_resolve_quant_mode_no_throw_with_models_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    import debug.debug_log as dl
    from src.core.config import AppSettings
    from src.models.quantization import resolve_quant_mode

    monkeypatch.delenv("AQUADUCT_DEBUG", raising=False)
    dl.apply_cli_debug("")
    try:
        dl.MODULE_DEBUG_FLAGS["models"] = True
        dl.invalidate_debug_cache()
        m = resolve_quant_mode(role="script", settings=AppSettings())
        assert isinstance(m, str)
        assert len(m) > 0
    finally:
        dl.MODULE_DEBUG_FLAGS["models"] = False
        dl.invalidate_debug_cache()


def test_invalidate_after_flag_change(monkeypatch: pytest.MonkeyPatch) -> None:
    import debug.debug_log as dl

    monkeypatch.delenv("AQUADUCT_DEBUG", raising=False)
    dl.apply_cli_debug("")
    try:
        dl.MODULE_DEBUG_FLAGS["ui"] = True
        dl.invalidate_debug_cache()
        assert dl.debug_enabled("ui")
        dl.MODULE_DEBUG_FLAGS["ui"] = False
        dl.invalidate_debug_cache()
        assert not dl.debug_enabled("ui")
    finally:
        dl.MODULE_DEBUG_FLAGS["ui"] = False
        dl.invalidate_debug_cache()


def test_all_dprint_categories_registered() -> None:
    """Every static ``dprint(\"cat\", ...)`` category string must exist in DEBUG_CATEGORIES."""
    from debug.debug_log import DEBUG_CATEGORIES

    registry = set(DEBUG_CATEGORIES)
    used = _dprint_categories_from_sources()
    unknown = sorted(used - registry)
    assert not unknown, f"dprint uses unknown categories: {unknown}"
