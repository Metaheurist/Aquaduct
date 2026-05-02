# `gpu_plan`

Placement breadcrumbs for **VRAM-first multi-GPU** paths: LLM Accelerate **`balanced`** / **`max_memory`** summaries and diffusers peer submodule moves after **`place_diffusion_pipeline`**.

Enable via **`AQUADUCT_DEBUG=gpu_plan`** or **`all`**. Code: [`src/gpu/multi_device/runtime.py`](../../src/gpu/multi_device/runtime.py), [`src/util/diffusion_placement.py`](../../src/util/diffusion_placement.py).
