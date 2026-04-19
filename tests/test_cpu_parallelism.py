from __future__ import annotations

import os

import pytest

from src.util import cpu_parallelism as cp


def test_effective_cpu_thread_count_respects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AQUADUCT_CPU_THREADS", raising=False)
    n = cp.effective_cpu_thread_count()
    assert 1 <= n <= 32

    monkeypatch.setenv("AQUADUCT_CPU_THREADS", "4")
    assert cp.effective_cpu_thread_count() == 4

    monkeypatch.setenv("AQUADUCT_CPU_THREADS", "999")
    assert cp.effective_cpu_thread_count() == 256


def test_configure_cpu_parallelism_sets_omp_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in cp._ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("AQUADUCT_CPU_THREADS", "3")
    cp._CONFIGURED = False
    try:
        cp.configure_cpu_parallelism()
        assert os.environ.get("OMP_NUM_THREADS") == "3"
    finally:
        cp._CONFIGURED = False


def test_configure_does_not_override_existing_omp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMP_NUM_THREADS", "7")
    cp._CONFIGURED = False
    try:
        cp.configure_cpu_parallelism()
        assert os.environ.get("OMP_NUM_THREADS") == "7"
    finally:
        cp._CONFIGURED = False


def test_pool_helpers_are_sane() -> None:
    assert cp.io_bound_pool_workers() >= 4
    assert 1 <= cp.disk_bound_verify_workers() <= 4


def test_torch_interop_cpu_only_uses_more_threads_than_accel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AQUADUCT_TORCH_INTEROP_THREADS", raising=False)
    n = 16
    cpu_only = cp.torch_interop_thread_count(n, accelerator_available=False)
    with_accel = cp.torch_interop_thread_count(n, accelerator_available=True)
    assert with_accel <= 8
    assert cpu_only >= with_accel


def test_torch_interop_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AQUADUCT_TORCH_INTEROP_THREADS", "5")
    assert cp.torch_interop_thread_count(99, accelerator_available=True) == 5
    assert cp.torch_interop_thread_count(99, accelerator_available=False) == 5
