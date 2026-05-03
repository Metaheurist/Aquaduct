from __future__ import annotations

import pytest

from src.models import torch_install as ti


@pytest.mark.parametrize(
    ("plat", "nvidia", "cuda_build", "expect"),
    [
        ("linux", True, False, True),
        ("win32", True, False, True),
        ("darwin", True, False, False),
        ("linux", False, False, False),
        ("linux", True, True, False),
    ],
)
def test_pytorch_cpu_wheel_with_nvidia_gpu_present(
    monkeypatch: pytest.MonkeyPatch, plat: str, nvidia: bool, cuda_build: bool | None, expect: bool
) -> None:
    monkeypatch.setattr(ti.sys, "platform", plat)
    monkeypatch.setattr(ti, "nvidia_gpu_likely_available", lambda: nvidia)
    monkeypatch.setattr(ti, "_installed_torch_is_cuda_build", lambda: cuda_build)
    assert ti.pytorch_cpu_wheel_with_nvidia_gpu_present() is expect


def test_format_pytorch_pip_cli_non_empty() -> None:
    cmd, _ = ti.build_pytorch_install_cmd(python_exe=None, upgrade=False)
    s = ti.format_pytorch_pip_cli(cmd)
    assert "pip" in s and "install" in s


def test_repo_root_contains_requirements_txt() -> None:
    r = ti.repo_root()
    assert (r / "requirements.txt").is_file()


def test_ui_project_root_matches_torch_repo_root() -> None:
    from UI.services.paths import project_root as pr

    assert pr().resolve() == ti.repo_root().resolve()
