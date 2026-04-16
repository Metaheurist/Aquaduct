from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .utils_vram import cleanup_vram, vram_guard


@dataclass(frozen=True)
class GeneratedImage:
    path: Path
    prompt: str


def _fallback_image(prompt: str, out_path: Path, *, size: int = 1024) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (size, size), (10, 10, 16))
    d = ImageDraw.Draw(img)
    # Best-effort font
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except Exception:
        font = ImageFont.load_default()
    txt = (prompt[:220] + "…") if len(prompt) > 220 else prompt
    d.text((40, 40), "CYBERPUNK VISUAL", fill=(0, 255, 200), font=font)
    d.text((40, 100), txt, fill=(240, 240, 240), font=font)
    img.save(out_path)


def _try_sdxl_turbo(model_id: str, prompts: list[str], out_dir: Path, *, steps: int = 1) -> list[GeneratedImage]:
    import torch
    from diffusers import AutoPipelineForText2Image

    out_dir.mkdir(parents=True, exist_ok=True)
    pipe = AutoPipelineForText2Image.from_pretrained(
        model_id,
        torch_dtype=torch.float16,
        variant="fp16",
    )
    if torch.cuda.is_available():
        pipe = pipe.to("cuda")
    else:
        # Still usable on CPU but slow; keep it anyway for correctness.
        pipe = pipe.to("cpu")

    results: list[GeneratedImage] = []
    for i, p in enumerate(prompts, start=1):
        img = pipe(
            prompt=p,
            num_inference_steps=max(1, int(steps)),
            guidance_scale=0.0,
            height=1024,
            width=1024,
        ).images[0]
        out_path = out_dir / f"img_{i:03d}.png"
        img.save(out_path)
        results.append(GeneratedImage(path=out_path, prompt=p))

    del pipe
    cleanup_vram()
    return results


def _try_sdxl_turbo_seeded(model_id: str, prompts: list[str], seeds: list[int], out_dir: Path, *, steps: int = 1) -> list[GeneratedImage]:
    import torch
    from diffusers import AutoPipelineForText2Image

    out_dir.mkdir(parents=True, exist_ok=True)
    pipe = AutoPipelineForText2Image.from_pretrained(
        model_id,
        torch_dtype=torch.float16,
        variant="fp16",
    )
    if torch.cuda.is_available():
        pipe = pipe.to("cuda")
    else:
        pipe = pipe.to("cpu")

    results: list[GeneratedImage] = []
    for i, (p, seed) in enumerate(zip(prompts, seeds), start=1):
        dev = "cuda" if str(pipe.device).startswith("cuda") else "cpu"
        gen = torch.Generator(device=dev).manual_seed(int(seed))
        img = pipe(
            prompt=p,
            num_inference_steps=max(1, int(steps)),
            guidance_scale=0.0,
            height=1024,
            width=1024,
            generator=gen,
        ).images[0]
        out_path = out_dir / f"img_{i:03d}.png"
        img.save(out_path)
        results.append(GeneratedImage(path=out_path, prompt=p))

    del pipe
    cleanup_vram()
    return results


def generate_images(
    *,
    sdxl_turbo_model_id: str,
    prompts: list[str],
    out_dir: Path,
    max_images: int | None = None,
    seeds: list[int] | None = None,
    steps: int = 1,
) -> list[GeneratedImage]:
    """
    Generates 5-10 images (1024x1024) for the provided prompts.
    Uses SDXL Turbo if available; otherwise generates readable placeholder images.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    prompts = [p.strip() for p in prompts if p.strip()]
    if not prompts:
        prompts = ["high-contrast cyberpunk UI, neon, sharp, cinematic, 9:16 composition"]
    if max_images is not None and max_images > 0:
        prompts = prompts[:max_images]
    if seeds is not None:
        seeds = [int(s) for s in seeds][: len(prompts)]
        if len(seeds) < len(prompts):
            # pad deterministically
            seeds = seeds + [int(seeds[-1]) + i + 1 for i in range(len(prompts) - len(seeds))]

    with vram_guard():
        try:
            if seeds is not None:
                return _try_sdxl_turbo_seeded(sdxl_turbo_model_id, prompts, seeds, out_dir, steps=steps)
            return _try_sdxl_turbo(sdxl_turbo_model_id, prompts, out_dir, steps=steps)
        except Exception:
            results: list[GeneratedImage] = []
            for i, p in enumerate(prompts, start=1):
                out_path = out_dir / f"img_{i:03d}.png"
                _fallback_image(p, out_path)
                results.append(GeneratedImage(path=out_path, prompt=p))
            return results

