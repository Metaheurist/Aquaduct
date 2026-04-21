"""
One-shot: after moving docs into subdirs, fix relative links. Run: python scripts/_fix_docs_paths.py
"""
from __future__ import annotations

import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"

# basename -> path under docs/
DOC_MAP: dict[str, str] = {
    "config.md": "reference/config.md",
    "models.md": "reference/models.md",
    "hardware.md": "reference/hardware.md",
    "vram.md": "reference/vram.md",
    "cli.md": "reference/cli.md",
    "main.md": "pipeline/main.md",
    "brain.md": "pipeline/brain.md",
    "artist.md": "pipeline/artist.md",
    "voice.md": "pipeline/voice.md",
    "editor.md": "pipeline/editor.md",
    "ffmpeg.md": "pipeline/ffmpeg.md",
    "performance.md": "pipeline/performance.md",
    "ui.md": "ui/ui.md",
    "branding.md": "ui/branding.md",
    "characters.md": "ui/characters.md",
    "api_generation.md": "integrations/api_generation.md",
    "crawler.md": "integrations/crawler.md",
    "elevenlabs.md": "integrations/elevenlabs.md",
    "tiktok.md": "integrations/tiktok.md",
    "youtube.md": "integrations/youtube.md",
    "building_windows_exe.md": "build/building_windows_exe.md",
    "model_youtube_demos.md": "build/model_youtube_demos.md",
}

CODE_UP = {
    "](../src/": "](../../src/",
    "](../UI/": "](../../UI/",
    "](../main.py": "](../../main.py",
    "](../build/": "](../../build/",
    "](../Model-Downloads/": "](../../Model-Downloads/",
    "](../DEPENDENCIES.md": "](../../DEPENDENCIES.md",
}


def rel_to(from_relpath: str, to_under_docs: str) -> str:
    """relpath from directory of from_relpath to file to_under_docs."""
    a = DOCS / from_relpath
    b = DOCS / to_under_docs
    r = os.path.relpath(b, a.parent).replace("\\", "/")
    if r == ".":
        r = b.name
    return r


def fix_markdown_file(path: Path) -> bool:
    from_rel = str(path.relative_to(DOCS))
    text = path.read_text(encoding="utf-8")
    o = text

    for a, b in CODE_UP.items():
        text = text.replace(a, b)

    def sub_docs(m: re.Match) -> str:
        body = m.group(1)
        if "#" in body:
            name, _, frag = body.partition("#")
            frag = "#" + frag
        else:
            name, frag = body, ""
        name = name.replace("docs/", "", 1)
        base = Path(name).name
        if base not in DOC_MAP:
            return m.group(0)
        r = rel_to(from_rel, DOC_MAP[base])
        return f"]({r}{frag})"

    text = re.sub(r"\]\(docs/([^)]+)\)", sub_docs, text)

    for base, under in DOC_MAP.items():
        r = rel_to(from_rel, under)
        text = re.sub(
            r"\]\(" + re.escape(base) + r"(#[^)]+)?\)",
            lambda m, rr=r: f"]({rr}{m.group(1) or ''})",
            text,
        )

    if text != o:
        path.write_text(text, encoding="utf-8", newline="\n")
        return True
    return False


def main() -> None:
    n = 0
    for p in sorted(DOCS.rglob("*.md")):
        if fix_markdown_file(p):
            n += 1
            print("fixed", p.relative_to(REPO))
    print(f"done; {n} files changed under docs/")


# Replace ``docs/basename`` paths anywhere in the repo (README, code comments, etc.)
OUTSIDE_REPLACEMENTS: list[tuple[str, str]] = [
    ("docs/api_generation.md", "docs/integrations/api_generation.md"),
    ("docs/artist.md", "docs/pipeline/artist.md"),
    ("docs/brain.md", "docs/pipeline/brain.md"),
    ("docs/branding.md", "docs/ui/branding.md"),
    ("docs/building_windows_exe.md", "docs/build/building_windows_exe.md"),
    ("docs/characters.md", "docs/ui/characters.md"),
    ("docs/cli.md", "docs/reference/cli.md"),
    ("docs/config.md", "docs/reference/config.md"),
    ("docs/crawler.md", "docs/integrations/crawler.md"),
    ("docs/editor.md", "docs/pipeline/editor.md"),
    ("docs/elevenlabs.md", "docs/integrations/elevenlabs.md"),
    ("docs/ffmpeg.md", "docs/pipeline/ffmpeg.md"),
    ("docs/hardware.md", "docs/reference/hardware.md"),
    ("docs/main.md", "docs/pipeline/main.md"),
    ("docs/model_youtube_demos.md", "docs/build/model_youtube_demos.md"),
    ("docs/models.md", "docs/reference/models.md"),
    ("docs/performance.md", "docs/pipeline/performance.md"),
    ("docs/tiktok.md", "docs/integrations/tiktok.md"),
    ("docs/ui.md", "docs/ui/ui.md"),
    ("docs/voice.md", "docs/pipeline/voice.md"),
    ("docs/vram.md", "docs/reference/vram.md"),
    ("docs/youtube.md", "docs/integrations/youtube.md"),
]


def main_outside() -> None:
    exts = {".md", ".py", ".ps1", ".spec", ".json", ".yml", ".yaml", ".txt", ".rc"}
    skip = {"scripts/_fix_docs_paths.py", "Model-Downloads", ".git"}
    n = 0
    for dirpath, dirnames, filenames in os.walk(REPO, topdown=True):
        dirnames[:] = [d for d in dirnames if d not in (".git", ".venv", "__pycache__", "node_modules")]
        p = Path(dirpath)
        rel = p.relative_to(REPO)
        for fn in filenames:
            fp = p / fn
            relp = str(fp.relative_to(REPO)).replace("\\", "/")
            if relp == "scripts/_fix_docs_paths.py":
                continue
            if fp.suffix.lower() not in exts:
                continue
            # Reorganized markdown lives under docs/{reference,pipeline,...}/; skip to avoid double edits
            if relp.startswith("docs/") and relp not in ("docs/README.md",):
                continue
            if not fp.is_file():
                continue
            t = fp.read_text(encoding="utf-8", errors="replace")
            o = t
            for a, b in OUTSIDE_REPLACEMENTS:
                t = t.replace(a, b)
            if t != o:
                fp.write_text(t, encoding="utf-8", newline="\n")
                n += 1
                print("repo replace:", relp)
    print(f"outside-docs: {n} files")


if __name__ == "__main__":
    import sys

    if "--docs-only" in sys.argv:
        main()
    elif "--repo-only" in sys.argv:
        main_outside()
    else:
        main()
        main_outside()
