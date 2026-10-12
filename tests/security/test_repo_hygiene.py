"""Tracked files must not contain credentials, and local secret stores must stay gitignored."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

_SECRET_PATTERNS = {
    "OpenAI key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}"),
    "Hugging Face token": re.compile(r"\bhf_[A-Za-z0-9]{30,}"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Replicate token": re.compile(r"\br8_[A-Za-z0-9]{30,}"),
    "Private key block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
_SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".mp4", ".mp3", ".wav", ".pdf", ".zip"}


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)


@pytest.fixture(scope="module")
def tracked_files() -> list[str]:
    if shutil.which("git") is None or not (REPO / ".git").exists():
        pytest.skip("git checkout required")
    res = _git("ls-files")
    if res.returncode != 0:
        pytest.skip("git ls-files failed")
    return [line for line in res.stdout.splitlines() if line]


def test_no_credentials_in_tracked_files(tracked_files: list[str]) -> None:
    hits: list[str] = []
    for rel in tracked_files:
        path = REPO / rel
        if path.suffix.lower() in _SKIP_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in _SECRET_PATTERNS.items():
            if pattern.search(text):
                hits.append(f"{rel}: {label}")
    assert not hits, "possible credentials committed:\n" + "\n".join(hits)


@pytest.mark.parametrize(
    "rel",
    [
        ".env",
        ".Aquaduct_data/ui_settings.json",
        ".Aquaduct_data/.ui_settings_fernet.key",
        ".Aquaduct_data/pipeline_queue.json",
    ],
)
def test_local_secret_stores_are_gitignored(tracked_files: list[str], rel: str) -> None:
    assert rel not in tracked_files
    assert _git("check-ignore", "-q", rel).returncode == 0, f"{rel} is not gitignored"
