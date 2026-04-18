from __future__ import annotations

from unittest.mock import patch

from src.torch_install import (
    _inject_pip_progress_bar_on,
    build_pytorch_install_cmd,
    nvidia_gpu_likely_available,
    pip_download_percent,
    pip_line_hint,
    prefer_pytorch_cu128_index,
    pytorch_cuda_wheel_index_url,
)


def test_nvidia_gpu_likely_available_false_when_no_smi(monkeypatch) -> None:
    monkeypatch.setattr("src.torch_install.shutil.which", lambda *_: None)
    monkeypatch.setattr("sys.platform", "linux")

    def fail_run(*_a, **_kw):
        class R:
            returncode = 1
            stdout = ""

        return R()

    monkeypatch.setattr("src.torch_install.subprocess.run", fail_run)
    assert nvidia_gpu_likely_available() is False


def test_build_pytorch_install_cmd_macos_uses_pypi(monkeypatch) -> None:
    monkeypatch.setattr("sys.platform", "darwin")
    cmd, desc = build_pytorch_install_cmd()
    assert "torch" in cmd and "torchvision" in cmd
    assert "--index-url" not in cmd
    assert "macOS" in desc or "PyPI" in desc


def test_build_pytorch_install_cmd_windows_with_smi_uses_cuda(monkeypatch) -> None:
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("src.torch_install.shutil.which", lambda *_: "nvidia-smi")

    def fake_run(*_a, **_kw):
        class R:
            returncode = 0
            stdout = "GPU 0: NVIDIA GeForce (UUID: GPU-aaaa)\n"

        return R()

    monkeypatch.setattr("src.torch_install.subprocess.run", fake_run)
    assert nvidia_gpu_likely_available() is True
    cmd, desc = build_pytorch_install_cmd()
    assert "cu124" in "".join(cmd) or "cu124" in desc


def test_build_pytorch_install_cmd_windows_uses_cu128_when_compute_cap_12(monkeypatch) -> None:
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("src.torch_install.shutil.which", lambda *_: "nvidia-smi")
    monkeypatch.setattr("src.torch_install._torch_reports_blackwell_or_newer", lambda: None)

    def fake_run(cmd, **_kw):
        argv = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)

        class R:
            pass

        r = R()
        r.returncode = 0
        if "compute_cap" in argv:
            r.stdout = "12.0\n"
        else:
            r.stdout = "GPU 0: NVIDIA GeForce RTX 5060 (UUID: GPU-aaaa)\n"
        return r

    monkeypatch.setattr("src.torch_install.subprocess.run", fake_run)
    assert prefer_pytorch_cu128_index() is True
    assert "cu128" in pytorch_cuda_wheel_index_url()
    cmd, desc = build_pytorch_install_cmd()
    assert "cu128" in "".join(cmd) and ("cu128" in desc or "Blackwell" in desc or "50" in desc)


def test_prefer_cu128_from_rtx50_name_when_no_compute_cap(monkeypatch) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("src.torch_install._torch_reports_blackwell_or_newer", lambda: None)
    monkeypatch.setattr("src.torch_install._nvidia_smi_compute_capability_major", lambda: None)

    def fake_run(cmd, **_kw):
        argv = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)

        class R:
            pass

        r = R()
        r.returncode = 0
        if "compute_cap" in argv:
            r.stdout = ""
            r.returncode = 1
        else:
            r.stdout = "GPU 0: NVIDIA GeForce RTX 5060 Laptop GPU (UUID: x)\n"
        return r

    monkeypatch.setattr("src.torch_install.subprocess.run", fake_run)
    monkeypatch.setattr("src.torch_install.shutil.which", lambda *_: "nvidia-smi")
    assert prefer_pytorch_cu128_index() is True


def test_build_pytorch_install_cmd_no_gpu_uses_cpu_index(monkeypatch) -> None:
    monkeypatch.setattr("sys.platform", "linux")

    def fake_run(*_a, **_kw):
        class R:
            returncode = 1
            stdout = ""

        return R()

    with patch("src.torch_install.shutil.which", return_value=None):
        monkeypatch.setattr("src.torch_install.subprocess.run", fake_run)
        assert nvidia_gpu_likely_available() is False
        cmd, _desc = build_pytorch_install_cmd()
        assert "cpu" in "".join(cmd).lower() or any("cpu" in x.lower() for x in cmd)


def test_pip_line_hint_collecting() -> None:
    h = pip_line_hint("Collecting numpy==2.0.0")
    assert h and "numpy" in h


def test_pip_line_hint_installing() -> None:
    h = pip_line_hint("Installing collected packages: foo, bar")
    assert h and "Installing" in h


def test_pip_line_hint_large_download() -> None:
    h = pip_line_hint(
        "Downloading https://example.org/torch.whl (2532.3 MB)"
    )
    assert h and "2532.3" in h and "MB" in h and "many minutes" in h


def test_pip_download_percent_tqdm_style() -> None:
    assert pip_download_percent(" 45%|████▌     | 1.2G/2.5G [00:30<00:35]") == 45
    assert pip_download_percent("| 80% |") == 80


def test_pip_download_percent_none_when_absent() -> None:
    assert pip_download_percent("Collecting numpy") is None


def test_inject_pip_progress_bar_on() -> None:
    base = ["py.exe", "-m", "pip", "install", "-r", "req.txt"]
    out = _inject_pip_progress_bar_on(base)
    assert out[:6] == ["py.exe", "-m", "pip", "install", "--progress-bar", "on"]
    assert _inject_pip_progress_bar_on(out) == out


def test_main_multiple_python_targets(monkeypatch) -> None:
    captured: list[str | None] = []

    def fake_then_rest(*, python_exe=None, **_kw):
        captured.append(python_exe)
        return 0, "ok"

    monkeypatch.setattr("src.torch_install.install_pytorch_then_rest", fake_then_rest)
    from src.torch_install import main

    assert main(["--with-rest", "--python", r"C:\a\python.exe", "--python", r"C:\b\python.exe"]) == 0
    assert captured == [r"C:\a\python.exe", r"C:\b\python.exe"]


def test_main_default_python_target(monkeypatch) -> None:
    captured: list[str | None] = []

    def fake_then_rest(*, python_exe=None, **_kw):
        captured.append(python_exe)
        return 0, "ok"

    monkeypatch.setattr("src.torch_install.install_pytorch_then_rest", fake_then_rest)
    from src.torch_install import main

    assert main(["--with-rest"]) == 0
    assert captured == [None]


def test_windows_branded_pip_python_distinct_roles(monkeypatch, tmp_path) -> None:
    """Branded copies get distinct basenames so Task Manager can tell pip workers apart."""
    fake_py = tmp_path / "python.exe"
    fake_py.write_bytes(b"fake")
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("sys.executable", str(fake_py))
    from src.torch_install import pip_python

    a = pip_python(None, role="torch")[0]
    b = pip_python(None, role="reqs")[0]
    c = pip_python(None, role="uninstall")[0]
    assert a != b != c
    assert "aquaduct-pip-torch" in a.replace("\\", "/")
    assert "aquaduct-pip-reqs" in b.replace("\\", "/")
    assert "aquaduct-pip-uninstall" in c.replace("\\", "/")
    assert (tmp_path / "aquaduct-pip-torch.exe").is_file()
