"""Local transformers load, generate, tokenizer helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, MutableMapping
from typing import Any

from src.core.config import AppSettings, get_paths
from src.core.models_dir import resolve_models_dir_for_pretrained
from src.models.model_manager import resolve_pretrained_load_path
from src.util.cuda_capabilities import (
    cuda_device_reported_by_torch,
    cuda_ok_for_llm_load,
    torch_cuda_kernels_work,
)
from src.util.llm_json_extract import parse_first_json_dict_from_llm_text
from src.util.utils_vram import cleanup_vram, vram_guard

from debug import dprint

def _emit_llm(
    on_llm_task: Callable[[str, int, str], None] | None, task: str, pct: int, msg: str
) -> None:
    if on_llm_task:
        on_llm_task(task, max(0, min(100, int(pct))), msg)


def _llm_max_input_tokens_cap_from_vram() -> int | None:
    """
    When VRAM is tight, lower the tokenizer cap so prefill (attention) does not OOM.

    Returns None if no extra cap should apply (caller uses base defaults only).
    Skipped when ``AQUADUCT_LLM_MAX_INPUT_TOKENS`` is set — user override wins.
    """
    import os

    if (os.environ.get("AQUADUCT_LLM_MAX_INPUT_TOKENS") or "").strip().isdigit():
        return None
    try:
        import torch

        if not cuda_device_reported_by_torch():
            return None
        total = int(torch.cuda.get_device_properties(0).total_memory)
    except Exception:
        return None
    # Prefill memory scales badly with sequence length; fp16 7–8B models already
    # consume most of an 8GB card — keep inputs conservative unless user overrides.
    _GIB = 1024**3
    if total < 10 * _GIB:
        return 1536
    if total < 12 * _GIB:
        return 2048
    if total < 16 * _GIB:
        return 3072
    if total < 24 * _GIB:
        return 4096
    return None


def _llm_max_input_tokens_cap(
    tokenizer: Any,
    *,
    model_id: str | None = None,
    inference_settings: AppSettings | None = None,
) -> int:
    """
    Cap prompt length for local ``generate()`` so long article/context strings do not
    blow VRAM during attention prefill (common on ~8GB GPUs).

    Override with env ``AQUADUCT_LLM_MAX_INPUT_TOKENS`` (integer; clamped 256–100000).
    Default: min(4096, tokenizer.model_max_length) when the latter is sane, else 4096,
    then further reduced on low-VRAM CUDA devices (see ``_llm_max_input_tokens_cap_from_vram``).
    When ``inference_settings`` is set, also min with the script inference profile
    (same effective VRAM as GPU policy fit badges for the script role).
    """
    import os

    raw = (os.environ.get("AQUADUCT_LLM_MAX_INPUT_TOKENS") or "").strip()
    if raw.isdigit():
        return max(256, min(int(raw), 100_000))
    default_cap = 4096
    mm = getattr(tokenizer, "model_max_length", None)
    if isinstance(mm, int) and 0 < mm < 100_000:
        base = min(default_cap, mm)
    else:
        base = default_cap
    vram_cap = _llm_max_input_tokens_cap_from_vram()
    if vram_cap is not None:
        base = min(base, vram_cap)
    if (model_id or "").strip() and inference_settings is not None:
        try:
            from src.models.inference_profiles import pick_script_profile, resolve_effective_vram_gb

            v = resolve_effective_vram_gb(kind="script", settings=inference_settings)
            sp = pick_script_profile((model_id or "").strip(), v)
            base = min(base, int(sp.max_input_tokens))
        except Exception:
            pass
    return base


def load_causal_lm_from_pretrained(
    load_path: str,
    *,
    try_4bit: bool = True,
    on_status: Callable[[str], None] | None = None,
    cuda_device_index: int | None = None,
    quant_mode: str | None = None,
    inference_settings: AppSettings | None = None,
    hub_model_id: str | None = None,
) -> Any:
    """
    Load ``AutoModelForCausalLM`` from disk or Hub id with an explicit quantization mode.

    ``quant_mode`` (preferred): ``auto`` | ``bf16`` | ``fp16`` | ``int8`` | ``nf4_4bit`` | ``cpu_offload``.
    When unset, falls back to legacy ``try_4bit`` boolean (``nf4_4bit`` if True else ``fp16``).

    ``inference_settings`` + ``hub_model_id`` enable optional VRAM-first multi-GPU sharding via Accelerate
    when ``multi_gpu_shard_mode`` is enabled (see docs).

    Each mode falls back to fp16 / CPU on failure with a status message.
    """
    import torch

    from src.models.hf_transformers_imports import causal_lm_stack
    from src.models.torch_dtypes import torch_float16

    AutoModelForCausalLM, _, BitsAndBytesConfig = causal_lm_stack()
    _fp16 = torch_float16()
    probe_cuda = torch_cuda_kernels_work()
    cuda_ok = cuda_ok_for_llm_load()

    def _status(msg: str) -> None:
        if on_status:
            on_status(msg)

    # Resolve effective mode from explicit quant_mode (preferred) or legacy try_4bit.
    qm = (quant_mode or "").strip().lower()
    if not qm:
        qm = "nf4_4bit" if bool(try_4bit) else "fp16"
    if qm not in ("auto", "bf16", "fp16", "int8", "nf4_4bit", "cpu_offload"):
        qm = "auto"

    def _legacy_single_gpu_device_map() -> dict[str, int]:
        if cuda_device_index is not None and cuda_ok:
            try:
                torch.cuda.set_device(int(cuda_device_index))
            except Exception:
                pass
            return {"": int(cuda_device_index)}
        return {"": 0}

    # Resolve ``auto`` before placement so Accelerate slicing matches the quantization chain.
    if qm == "auto":
        try:
            from src.models.hardware import list_cuda_gpus
            from src.models.quantization import pick_auto_mode

            gpus = list_cuda_gpus()
            v = None
            if gpus and cuda_device_index is not None:
                for g in gpus:
                    if g.index == int(cuda_device_index):
                        v = g.total_vram_gb
                        break
            elif gpus:
                v = gpus[0].total_vram_gb
            qm = str(pick_auto_mode(role="script", repo_id="", vram_gb=v, cuda_ok=True))
        except Exception:
            qm = "nf4_4bit"

    legacy_dm = _legacy_single_gpu_device_map()

    from src.gpu.multi_device.runtime import resolve_llm_device_map_and_max_memory

    float_dm, float_mm, plan_note = resolve_llm_device_map_and_max_memory(
        settings=inference_settings,
        hub_model_id=str(hub_model_id or "").strip(),
        cuda_device_index=cuda_device_index,
        effective_quant=qm,
    )
    try:
        from debug import debug_enabled as _dbg_en
        from debug import dprint as _dprt

        if _dbg_en("gpu_plan"):
            _dprt("gpu_plan", "llm_placement", plan_note, f"quant_resolved={qm!r}", f"device_map_hint={float_dm!r}")
    except Exception:
        pass

    def _bf16_dtype() -> Any:
        try:
            return torch.bfloat16
        except Exception:
            return _fp16

    def _from_pretrained(
        *,
        quantization_config: Any | None,
        device_map: Any,
        dtype: Any,
        max_memory: dict[int | str, str] | None = None,
    ) -> Any:
        extra_kw: dict[str, Any] = {}
        if max_memory is not None:
            extra_kw["max_memory"] = max_memory
            if isinstance(max_memory, dict) and "disk" in max_memory:
                try:
                    from src.core.config import get_paths

                    od = get_paths().cache_dir / "accelerate_offload"
                    od.mkdir(parents=True, exist_ok=True)
                    extra_kw["offload_folder"] = str(od)
                except Exception:
                    pass
        if quantization_config is not None:
            try:
                return AutoModelForCausalLM.from_pretrained(
                    load_path,
                    quantization_config=quantization_config,
                    device_map=device_map,
                    dtype=dtype,
                    low_cpu_mem_usage=True,
                    trust_remote_code=True,
                    **extra_kw,
                )
            except TypeError:
                try:
                    return AutoModelForCausalLM.from_pretrained(
                        load_path,
                        quantization_config=quantization_config,
                        device_map=device_map,
                        torch_dtype=dtype,
                        low_cpu_mem_usage=True,
                        trust_remote_code=True,
                        **extra_kw,
                    )
                except TypeError:
                    return AutoModelForCausalLM.from_pretrained(
                        load_path,
                        quantization_config=quantization_config,
                        device_map=device_map,
                        torch_dtype=dtype,
                        trust_remote_code=True,
                        **extra_kw,
                    )
        try:
            return AutoModelForCausalLM.from_pretrained(
                load_path,
                device_map=device_map,
                dtype=dtype,
                low_cpu_mem_usage=True,
                trust_remote_code=True,
                **extra_kw,
            )
        except TypeError:
            try:
                return AutoModelForCausalLM.from_pretrained(
                    load_path,
                    device_map=device_map,
                    torch_dtype=dtype,
                    low_cpu_mem_usage=True,
                    trust_remote_code=True,
                    **extra_kw,
                )
            except TypeError:
                return AutoModelForCausalLM.from_pretrained(
                    load_path,
                    device_map=device_map,
                    torch_dtype=dtype,
                    trust_remote_code=True,
                    **extra_kw,
                )

    if not cuda_ok:
        import os

        _allow_cpu = (os.environ.get("AQUADUCT_ALLOW_CPU_TORCH_WITH_NVIDIA", "").strip().lower() in ("1", "true", "yes", "on"))
        if not _allow_cpu:
            try:
                from src.models import torch_install as ti

                if ti.pytorch_cpu_wheel_with_nvidia_gpu_present():
                    raise RuntimeError(ti.cuda_torch_required_message_for_nvidia_host())
            except RuntimeError:
                raise
            except Exception:
                pass
        _status("CUDA not available; loading LLM on CPU (slower)…")
        return _from_pretrained(quantization_config=None, device_map="cpu", dtype=_fp16)
    if cuda_ok and not probe_cuda:
        _status(
            "CUDA device detected — using GPU despite failed kernel probe; "
            "if load errors, reinstall PyTorch for your CUDA/driver build."
        )

    def _try_bnb_4bit() -> Any:
        bnb = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=_fp16,
        )
        _status("Loading model (NF4 4-bit)…")
        return _from_pretrained(quantization_config=bnb, device_map=legacy_dm, dtype=_fp16)

    def _try_bnb_8bit() -> Any:
        bnb = BitsAndBytesConfig(load_in_8bit=True)
        _status("Loading model (INT8 / 8-bit)…")
        return _from_pretrained(quantization_config=bnb, device_map=legacy_dm, dtype=_fp16)

    def _try_bf16() -> Any:
        _status("Loading model (BF16)…")
        return _from_pretrained(quantization_config=None, device_map=float_dm, dtype=_bf16_dtype(), max_memory=float_mm)

    def _try_fp16() -> Any:
        _status("Loading model (FP16)…")
        return _from_pretrained(quantization_config=None, device_map=float_dm, dtype=_fp16, max_memory=float_mm)

    def _try_cpu() -> Any:
        _status("Loading model on CPU offload (FP16)…")
        return _from_pretrained(quantization_config=None, device_map="cpu", dtype=_fp16)

    chain: list[tuple[str, Any]] = []
    if qm == "nf4_4bit":
        chain = [("NF4 4-bit", _try_bnb_4bit), ("INT8", _try_bnb_8bit), ("FP16", _try_fp16), ("CPU FP16", _try_cpu)]
    elif qm == "int8":
        chain = [("INT8", _try_bnb_8bit), ("NF4 4-bit", _try_bnb_4bit), ("FP16", _try_fp16), ("CPU FP16", _try_cpu)]
    elif qm == "bf16":
        chain = [("BF16", _try_bf16), ("FP16", _try_fp16), ("INT8", _try_bnb_8bit), ("CPU FP16", _try_cpu)]
    elif qm == "cpu_offload":
        chain = [("CPU FP16", _try_cpu), ("FP16", _try_fp16)]
    else:  # fp16 / fallback
        chain = [("FP16", _try_fp16), ("INT8", _try_bnb_8bit), ("NF4 4-bit", _try_bnb_4bit), ("CPU FP16", _try_cpu)]

    last_err: Exception | None = None
    for label, fn in chain:
        try:
            return fn()
        except Exception as e:
            last_err = e
            _status(f"{label} load failed ({type(e).__name__}); falling back…")
    if last_err is not None:
        raise last_err
    return _try_fp16()


def _prepare_torch_for_llm_load() -> None:
    import torch

    try:
        from src.util.cpu_parallelism import apply_torch_cpu_settings

        apply_torch_cpu_settings(torch)
    except Exception:
        pass

    try:
        if cuda_device_reported_by_torch():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
    except Exception:
        pass


def _load_causal_lm_pair(
    model_id: str,
    *,
    on_llm_task: Callable[[str, int, str], None] | None = None,
    try_llm_4bit: bool = True,
    llm_cuda_device_index: int | None = None,
    inference_settings: AppSettings | None = None,
    quant_mode: str | None = None,
) -> tuple[Any, Any]:
    """Load tokenizer + causal LM once; caller must `_dispose_causal_lm_pair` when done."""
    _prepare_torch_for_llm_load()

    from src.models.hf_access import ensure_hf_token_in_env
    from src.models.hf_transformers_imports import causal_lm_stack

    ensure_hf_token_in_env(hf_token="")

    _, AutoTokenizer, _ = causal_lm_stack()

    def _load_status(detail: str) -> None:
        _emit_llm(on_llm_task, "llm_load", 55, detail)

    load_path = resolve_pretrained_load_path(
        model_id,
        models_dir=resolve_models_dir_for_pretrained(inference_settings),
    )

    try:
        from src.util.vram_watchdog import check_cuda_headroom

        check_cuda_headroom(llm_cuda_device_index, stage=f"LLM load ({model_id})")
    except RuntimeError:
        raise
    except Exception:
        pass

    _emit_llm(on_llm_task, "llm_load", 0, "Loading tokenizer…")
    tokenizer = AutoTokenizer.from_pretrained(load_path, use_fast=True, trust_remote_code=True)
    _emit_llm(on_llm_task, "llm_load", 25, "Tokenizer ready")

    _emit_llm(on_llm_task, "llm_load", 30, "Loading model weights…")
    _qmode = quant_mode
    if not _qmode and inference_settings is not None:
        _qmode = str(getattr(inference_settings, "script_quant_mode", "") or "") or None
    model = load_causal_lm_from_pretrained(
        load_path,
        try_4bit=bool(try_llm_4bit),
        on_status=_load_status,
        cuda_device_index=llm_cuda_device_index,
        quant_mode=_qmode,
        inference_settings=inference_settings,
        hub_model_id=model_id,
    )
    _emit_llm(on_llm_task, "llm_load", 100, "Model loaded")
    return tokenizer, model


def _dispose_causal_lm_pair(model: Any, tokenizer: Any) -> None:
    try:
        del model
    except Exception:
        pass
    try:
        del tokenizer
    except Exception:
        pass
    cleanup_vram()


def _script_generation_max_new_tokens(
    requested: int,
    *,
    model_id: str,
    inference_settings: AppSettings | None,
    relax_short_json_batch: bool = False,
) -> int:
    """Clamp completion length by script VRAM profile; optional headroom for compact multi-key JSON."""
    req = max(1, int(requested))
    if inference_settings is None:
        return min(req, 4096)
    try:
        from src.models.inference_profiles import pick_script_profile, resolve_effective_vram_gb

        v = resolve_effective_vram_gb(kind="script", settings=inference_settings)
        sp = pick_script_profile((model_id or "").strip(), v)
        cap = int(sp.max_new_tokens)
    except Exception:
        return min(req, 4096)
    if relax_short_json_batch:
        relaxed = min(2048, max(cap, min(req, cap * 4)))
        return min(req, relaxed)
    return min(req, cap)


def _pipeline_prompt_body_for_chat_template(prompt: str) -> str:
    """Strip legacy Alpaca wrappers so chat_template sees a single user turn body only."""
    s = str(prompt or "").strip()
    if "### Response:" in s:
        head = s.split("### Response:", 1)[0].strip()
        if "### Instruction:" in head:
            return head.split("### Instruction:", 1)[-1].strip()
        return head
    return s


def _generate_with_loaded_causal_lm(
    model: Any,
    tokenizer: Any,
    model_id: str,
    prompt: str,
    *,
    on_llm_task: Callable[[str, int, str], None] | None = None,
    max_new_tokens: int = 650,
    inference_settings: AppSettings | None = None,
    cancel_event: Any | None = None,
    relax_short_json_batch: bool = False,
) -> str:
    """Single decode pass using an already-loaded causal LM (multistage refinement session)."""
    import os

    import torch

    def _stderr(msg: str) -> None:
        if not on_llm_task:
            import sys

            print(f"[Aquaduct] {msg}", file=sys.stderr, flush=True)

    _cap = _llm_max_input_tokens_cap(tokenizer, model_id=model_id, inference_settings=inference_settings)
    max_new_use = _script_generation_max_new_tokens(
        max_new_tokens,
        model_id=model_id,
        inference_settings=inference_settings,
        relax_short_json_batch=relax_short_json_batch,
    )
    force_alpaca = os.environ.get("AQUADUCT_PIPELINE_FORCE_ALPACA", "").strip() == "1"
    template = getattr(tokenizer, "chat_template", None)
    use_chat_template = bool(template) and not force_alpaca
    if use_chat_template:
        msgs = [{"role": "user", "content": _pipeline_prompt_body_for_chat_template(prompt)}]
        try:
            enc = tokenizer.apply_chat_template(
                msgs,
                add_generation_prompt=True,
                return_dict=True,
                return_tensors="pt",
                truncation=True,
                max_length=_cap,
            )
        except TypeError:
            enc = tokenizer.apply_chat_template(
                msgs,
                add_generation_prompt=True,
                tokenize=True,
                return_tensors="pt",
                truncation=True,
                max_length=_cap,
            )
            if not isinstance(enc, dict):
                enc = {"input_ids": enc}
        if not isinstance(enc, dict):
            enc = dict(enc)
        inputs = {k: v.to(model.device) for k, v in enc.items()}
    else:
        full = f"### Instruction:\n{prompt}\n\n### Response:\n"
        inputs = tokenizer(
            full,
            return_tensors="pt",
            truncation=True,
            max_length=_cap,
        ).to(model.device)
    prompt_len = int(inputs["input_ids"].shape[1])

    if cuda_device_reported_by_torch():
        torch.cuda.empty_cache()

    eos_ids = _eos_token_id_candidates(tokenizer)
    if not eos_ids:
        e = getattr(tokenizer, "eos_token_id", None)
        if isinstance(e, int):
            eos_ids = [e]

    _emit_llm(on_llm_task, "llm_generate", 0, "Starting generation…")
    _stderr("LLM inference starting (streamed progress when supported).")
    dprint("brain", "generate() starting")

    raw_new: str | None = None

    try:
        from threading import Thread

        from src.models.hf_transformers_imports import text_iterator_streamer_cls

        TextIteratorStreamer = text_iterator_streamer_cls()

        streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
        generation_kwargs: dict[str, Any] = {
            **inputs,
            "streamer": streamer,
            "max_new_tokens": max_new_use,
            "do_sample": True,
            "temperature": 0.7,
            "top_p": 0.9,
            "repetition_penalty": 1.08,
        }
        if eos_ids:
            generation_kwargs["eos_token_id"] = eos_ids[0] if len(eos_ids) == 1 else eos_ids

        def _run_gen() -> None:
            with torch.inference_mode():
                if cuda_device_reported_by_torch():
                    torch.cuda.empty_cache()
                model.generate(**generation_kwargs)

        th = Thread(target=_run_gen, daemon=True)
        th.start()
        chunks: list[str] = []
        n_tok = 0
        for text in streamer:
            if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                break
            chunks.append(text)
            n_tok += 1
            pct = min(99, int(100 * n_tok / max(1, max_new_use)))
            _emit_llm(
                on_llm_task,
                "llm_generate",
                pct,
                f"Generating tokens ({n_tok}/{max_new_use})",
            )
        th.join(timeout=7200)
        raw_new = "".join(chunks)
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            _emit_llm(on_llm_task, "llm_generate", 100, "Cancelled")
            return raw_new
        _emit_llm(on_llm_task, "llm_generate", 100, "Generation finished")
    except Exception as e:
        dprint("brain", "streamed generation failed, falling back", str(e))
        _emit_llm(on_llm_task, "llm_generate", 10, "Fallback: one-shot generate…")
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            return (raw_new or "").strip()
        gen_fallback: dict[str, Any] = {
            **inputs,
            "max_new_tokens": max_new_use,
            "do_sample": True,
            "temperature": 0.7,
            "top_p": 0.9,
            "repetition_penalty": 1.08,
        }
        if eos_ids:
            gen_fallback["eos_token_id"] = eos_ids[0] if len(eos_ids) == 1 else eos_ids
        with torch.inference_mode():
            if cuda_device_reported_by_torch():
                torch.cuda.empty_cache()
            out = model.generate(**gen_fallback)
        _emit_llm(on_llm_task, "llm_generate", 100, "Decoding…")
        if use_chat_template:
            raw_new = tokenizer.decode(out[0][prompt_len:], skip_special_tokens=True)
        else:
            text_full = tokenizer.decode(out[0], skip_special_tokens=True)
            if "### Response:" in text_full:
                raw_new = text_full.split("### Response:", 1)[1].strip()
            else:
                raw_new = text_full

    assert raw_new is not None
    return raw_new


def _eos_token_id_candidates(tokenizer: Any) -> list[int]:
    out: list[int] = []
    base = getattr(tokenizer, "eos_token_id", None)
    if isinstance(base, int):
        out.append(base)
    for tok in ("<|eot_id|>", "<|im_end|>"):
        try:
            tid = tokenizer.convert_tokens_to_ids(tok)
            if isinstance(tid, int) and tid >= 0 and tid not in out:
                out.append(tid)
        except Exception:
            continue
    if not out and base is not None:
        return [int(base)]
    return out


def _generate_chat_with_loaded_causal_lm(
    model: Any,
    tokenizer: Any,
    model_id: str,
    messages: list[dict[str, str]],
    *,
    on_llm_task: Callable[[str, int, str], None] | None = None,
    max_new_tokens: int = 256,
    inference_settings: AppSettings | None = None,
    cancel_event: Any | None = None,
    relax_short_json_batch: bool = False,
) -> str:
    """Chat-template decode when available; otherwise fall back to Alpaca-style flat prompt."""
    import torch

    msgs = [m for m in messages if str(m.get("content", "")).strip()]
    if not msgs:
        return ""

    template = getattr(tokenizer, "chat_template", None)
    if not template:
        lines = []
        for m in msgs:
            role = str(m.get("role", "user")).upper()
            body = str(m.get("content", "")).strip()
            lines.append(f"{role}: {body}")
        prompt = "\n\n".join(lines)
        return _generate_with_loaded_causal_lm(
            model,
            tokenizer,
            model_id,
            prompt,
            on_llm_task=on_llm_task,
            max_new_tokens=max_new_tokens,
            inference_settings=inference_settings,
            cancel_event=cancel_event,
            relax_short_json_batch=relax_short_json_batch,
        )

    _cap = _llm_max_input_tokens_cap(tokenizer, model_id=model_id, inference_settings=inference_settings)
    max_new_use = _script_generation_max_new_tokens(
        max_new_tokens,
        model_id=model_id,
        inference_settings=inference_settings,
        relax_short_json_batch=relax_short_json_batch,
    )

    try:
        enc = tokenizer.apply_chat_template(
            msgs,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
            truncation=True,
            max_length=_cap,
        )
    except TypeError:
        enc = tokenizer.apply_chat_template(
            msgs,
            add_generation_prompt=True,
            tokenize=True,
            return_tensors="pt",
            truncation=True,
            max_length=_cap,
        )
        if not isinstance(enc, dict):
            enc = {"input_ids": enc}

    if not isinstance(enc, dict):
        enc = dict(enc)
    inputs = {k: v.to(model.device) for k, v in enc.items()}

    _emit_llm(on_llm_task, "llm_generate", 0, "Starting generation…")
    if cuda_device_reported_by_torch():
        torch.cuda.empty_cache()

    prompt_len = int(inputs["input_ids"].shape[1])
    eos_ids = _eos_token_id_candidates(tokenizer)
    if not eos_ids:
        e = getattr(tokenizer, "eos_token_id", None)
        if isinstance(e, int):
            eos_ids = [e]

    class _StopUserPrefix:
        def __init__(self, tok: Any, start_len: int) -> None:
            self._tok = tok
            self._start = start_len

        def __call__(self, input_ids, scores, **kwargs) -> bool:
            _seq = input_ids[0]
            if _seq.shape[-1] <= self._start:
                return False
            tail = self._tok.decode(_seq[self._start :], skip_special_tokens=True)
            return "\nUser:" in tail

    try:
        from transformers import StoppingCriteria, StoppingCriteriaList

        class _PyStop(StoppingCriteria):
            def __init__(self, fn) -> None:  # type: ignore[no-untyped-def]
                self._fn = fn

            def __call__(self, input_ids, scores, **kwargs) -> bool:  # type: ignore[no-untyped-def]
                return bool(self._fn(input_ids, scores, **kwargs))

        stop_list = StoppingCriteriaList([_PyStop(_StopUserPrefix(tokenizer, prompt_len))])
    except Exception:
        stop_list = None

    raw_new: str | None = None
    try:
        from threading import Thread

        from src.models.hf_transformers_imports import text_iterator_streamer_cls

        TextIteratorStreamer = text_iterator_streamer_cls()
        streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
        gen_kw: dict[str, Any] = {
            **inputs,
            "streamer": streamer,
            "max_new_tokens": max_new_use,
            "do_sample": True,
            "temperature": 0.7,
            "top_p": 0.9,
            "repetition_penalty": 1.08,
        }
        if eos_ids:
            gen_kw["eos_token_id"] = eos_ids[0] if len(eos_ids) == 1 else eos_ids
        if stop_list is not None:
            gen_kw["stopping_criteria"] = stop_list

        def _run_gen() -> None:
            with torch.inference_mode():
                if cuda_device_reported_by_torch():
                    torch.cuda.empty_cache()
                model.generate(**gen_kw)

        th = Thread(target=_run_gen, daemon=True)
        th.start()
        chunks: list[str] = []
        n_tok = 0
        for text in streamer:
            if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                break
            chunks.append(text)
            n_tok += 1
            pct = min(99, int(100 * n_tok / max(1, max_new_use)))
            _emit_llm(
                on_llm_task,
                "llm_generate",
                pct,
                f"Generating tokens ({n_tok}/{max_new_use})",
            )
        th.join(timeout=7200)
        raw_new = "".join(chunks)
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            _emit_llm(on_llm_task, "llm_generate", 100, "Cancelled")
            return raw_new
        _emit_llm(on_llm_task, "llm_generate", 100, "Generation finished")
    except Exception as e:
        dprint("brain", "chat streamed generation failed, falling back", str(e))
        _emit_llm(on_llm_task, "llm_generate", 10, "Fallback: one-shot generate…")
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            return (raw_new or "").strip()
        gen_kw2: dict[str, Any] = {
            **inputs,
            "max_new_tokens": max_new_use,
            "do_sample": True,
            "temperature": 0.7,
            "top_p": 0.9,
            "repetition_penalty": 1.08,
        }
        if eos_ids:
            gen_kw2["eos_token_id"] = eos_ids[0] if len(eos_ids) == 1 else eos_ids
        if stop_list is not None:
            gen_kw2["stopping_criteria"] = stop_list
        with torch.inference_mode():
            if cuda_device_reported_by_torch():
                torch.cuda.empty_cache()
            out = model.generate(**gen_kw2)
        _emit_llm(on_llm_task, "llm_generate", 100, "Decoding…")
        text_full = tokenizer.decode(out[0][prompt_len:], skip_special_tokens=True)
        raw_new = text_full

    assert raw_new is not None
    return raw_new.strip()


def _infer_text_with_optional_holder(
    model_id: str,
    prompt: str,
    *,
    llm_holder: MutableMapping[str, Any] | None,
    messages: list[dict[str, str]] | None = None,
    on_llm_task: Callable[[str, int, str], None] | None = None,
    max_new_tokens: int = 650,
    try_llm_4bit: bool = True,
    llm_cuda_device_index: int | None = None,
    inference_settings: AppSettings | None = None,
    quant_mode: str | None = None,
    cancel_event: Any | None = None,
    relax_short_json_batch: bool = False,
) -> str:
    """
    Run one causal-LM inference. If ``llm_holder`` is provided, reuse or swap weights in-place;
    otherwise load, infer, dispose (legacy one-shot behaviour).

    When ``messages`` is set (chat template path), ``prompt`` is ignored.
    """
    mid = str(model_id or "").strip()
    if not mid:
        raise RuntimeError("_infer_text_with_optional_holder requires model_id.")
    use_chat = messages is not None
    if use_chat:
        if not isinstance(messages, list) or not messages:
            raise RuntimeError("messages must be a non-empty list when provided.")
    elif not str(prompt or "").strip():
        raise RuntimeError("_infer_text_with_optional_holder requires prompt or messages.")

    qm = quant_mode
    if qm is None and inference_settings is not None:
        qm = str(getattr(inference_settings, "script_quant_mode", "") or "") or None

    if llm_holder is None:
        tokenizer, model = _load_causal_lm_pair(
            mid,
            on_llm_task=on_llm_task,
            try_llm_4bit=try_llm_4bit,
            llm_cuda_device_index=llm_cuda_device_index,
            inference_settings=inference_settings,
            quant_mode=qm,
        )
        try:
            if use_chat:
                return _generate_chat_with_loaded_causal_lm(
                    model,
                    tokenizer,
                    mid,
                    messages,  # type: ignore[arg-type]
                    on_llm_task=on_llm_task,
                    max_new_tokens=max_new_tokens,
                    inference_settings=inference_settings,
                    cancel_event=cancel_event,
                    relax_short_json_batch=relax_short_json_batch,
                )
            return _generate_with_loaded_causal_lm(
                model,
                tokenizer,
                mid,
                prompt,
                on_llm_task=on_llm_task,
                max_new_tokens=max_new_tokens,
                inference_settings=inference_settings,
                cancel_event=cancel_event,
                relax_short_json_batch=relax_short_json_batch,
            )
        finally:
            _dispose_causal_lm_pair(model, tokenizer)

    prev_id = str(llm_holder.get("hub_model_id") or "").strip()
    if llm_holder.get("model") is not None and prev_id and prev_id != mid:
        _dispose_causal_lm_pair(llm_holder["model"], llm_holder.get("tokenizer"))
        llm_holder["model"] = None
        llm_holder["tokenizer"] = None
        llm_holder["hub_model_id"] = ""

    if llm_holder.get("model") is None:
        tok, mod = _load_causal_lm_pair(
            mid,
            on_llm_task=on_llm_task,
            try_llm_4bit=try_llm_4bit,
            llm_cuda_device_index=llm_cuda_device_index,
            inference_settings=inference_settings,
            quant_mode=qm,
        )
        llm_holder["tokenizer"] = tok
        llm_holder["model"] = mod
        llm_holder["hub_model_id"] = mid

    if use_chat:
        return _generate_chat_with_loaded_causal_lm(
            llm_holder["model"],
            llm_holder["tokenizer"],
            mid,
            messages,  # type: ignore[arg-type]
            on_llm_task=on_llm_task,
            max_new_tokens=max_new_tokens,
            inference_settings=inference_settings,
            cancel_event=cancel_event,
            relax_short_json_batch=relax_short_json_batch,
        )
    return _generate_with_loaded_causal_lm(
        llm_holder["model"],
        llm_holder["tokenizer"],
        mid,
        prompt,
        on_llm_task=on_llm_task,
        max_new_tokens=max_new_tokens,
        inference_settings=inference_settings,
        cancel_event=cancel_event,
        relax_short_json_batch=relax_short_json_batch,
    )


def _generate_with_transformers(
    model_id: str,
    prompt: str,
    *,
    on_llm_task: Callable[[str, int, str], None] | None = None,
    max_new_tokens: int = 650,
    try_llm_4bit: bool = True,
    llm_cuda_device_index: int | None = None,
    inference_settings: AppSettings | None = None,
    quant_mode: str | None = None,
) -> str:
    return _infer_text_with_optional_holder(
        model_id,
        prompt,
        llm_holder=None,
        on_llm_task=on_llm_task,
        max_new_tokens=max_new_tokens,
        try_llm_4bit=try_llm_4bit,
        llm_cuda_device_index=llm_cuda_device_index,
        inference_settings=inference_settings,
        quant_mode=quant_mode,
    )
