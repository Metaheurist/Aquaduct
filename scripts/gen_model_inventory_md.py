# Regenerate docs/reference/model_inventory.md — run from repo root:
#   python scripts/gen_model_inventory_md.py
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.models.hardware import vram_requirement_hint
from src.models.model_manager import model_options
from src.models.model_tiers import api_tier_for_model, local_tier_for_repo, tier_label
from src.settings.api_model_catalog import PROVIDERS, default_models_for_provider


def kind_to_vram_kind(k: str) -> str:
    return k if k in ("script", "image", "video", "voice") else "script"


def run() -> str:
    lines: list[str] = []
    lines.append("# Model inventory (local + API)\n\n")
    lines.append("Curated **local** models come from `model_options()`; **API** providers from `api_model_catalog.PROVIDERS` and `default_models_for_provider`.\n\n")
    lines.append("**Tiers** (`[Pro]`, `[Standard]`, `[Lite]`) are defined in `src/models/model_tiers.py`.\n\n")
    lines.append("**Local VRAM** is the **heuristic** label from `vram_requirement_hint()` in `src/models/hardware.py` (quantization, offload, and settings change real needs). **API** rows use the provider’s cloud—**no local GPU** for that step.\n\n")
    lines.append("---\n\n## Local (Hugging Face) — `Model` tab, execution: Local\n\n")
    lines.append("| Role | `repo_id` | Tier | Size hint (UI) | Speed | Typical GPU / RAM (heuristic) |\n")
    lines.append("|------|-----------|------|----------------|-------|----------------------------------|\n")
    for o in model_options():
        k = kind_to_vram_kind(o.kind)
        vr = vram_requirement_hint(
            kind=k,
            repo_id=o.repo_id,
            speed=o.speed,
            pair_image_repo_id=str(getattr(o, "pair_image_repo_id", "") or ""),
        )
        t = local_tier_for_repo(o.repo_id)
        sh = (getattr(o, "size_hint", "") or "—").replace("|", "\\|")
        lines.append(
            f"| {o.kind} | `{o.repo_id}` | {tier_label(t)} | {sh} | {o.speed} | {vr.replace('|', ' ')} |\n"
        )

    lines.append("\n---\n\n## API — `Model` + `API` tab, execution: API\n\n")
    lines.append("One row per **provider + role + default model** from `default_models_for_provider`. Custom model ids and Replicate version strings are also supported in the UI.\n\n")
    lines.append("| Provider | Role | `model` id | Tier | Local GPU for this step | Env keys (first listed) |\n")
    lines.append("|----------|------|------------|------|--------------------------|------------------------|\n")
    for p in PROVIDERS:
        for role in p.roles:
            models = default_models_for_provider(p.id, role)  # type: ignore[arg-type]
            for mid in models:
                tr = api_tier_for_model(p.id, mid)
                env = ", ".join(p.env_key_names[:5])
                if len(p.env_key_names) > 5:
                    env += ", …"
                lines.append(
                    f"| {p.display_name} | {role} | `{mid}` | {tier_label(tr)} | **No** | {env} |\n"
                )
    lines.append("\n### Notes\n\n")
    lines.append(
        "- **OpenAI `video` role:** `default_models_for_provider` falls back to the provider’s full `model_slugs` "
        "tuple, so the Video row may list chat/image/TTS ids—use a real Pro text-to-video id from the provider’s docs, "
        "or choose **Kling / Magic Hour / Replicate** for motion.\n"
    )
    lines.append("- **Regenerate:** `python scripts/gen_model_inventory_md.py` from the repo root.\n")
    return "".join(lines)


if __name__ == "__main__":
    out = run()
    p = ROOT / "docs" / "reference" / "model_inventory.md"
    p.write_text(out, encoding="utf-8")
    print(f"Wrote {p}")
