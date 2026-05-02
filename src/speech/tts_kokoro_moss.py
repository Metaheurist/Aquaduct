"""
Optional local TTS: Kokoro-82M (hexgrad) and MOSS-VoiceGenerator (OpenMOSS).

Both require extra Python deps and (for MOSS) a strong GPU; failure falls back to pyttsx3
in :mod:`src.speech.voice`.
"""
from __future__ import annotations

import random
from pathlib import Path

# Hub ids (must match Model tab / settings)
KOKORO_HUB = "hexgrad/Kokoro-82M"
MOSS_VG_HUB = "OpenMOSS-Team/MOSS-VoiceGenerator"

# Well-known social presets (per VOICES / Kokoro community naming)
KOKORO_SOCIAL_PRESETS: tuple[str, ...] = ("af_bella", "af_nicole", "am_adam")
_KOKORO_ALIASES: dict[str, str] = {
    "bella": "af_bella",
    "af_bella": "af_bella",
    "nicole": "af_nicole",
    "af_nicole": "af_nicole",
    "adam": "am_adam",
    "am_adam": "am_adam",
}

DEFAULT_MOSS_INSTRUCTION = (
    "Engaging short-form narrator, clear American English, confident and warm, suitable for social media."
)


def is_kokoro_repo(model_id: str) -> bool:
    return (model_id or "").strip() == KOKORO_HUB


def is_moss_vg_repo(model_id: str) -> bool:
    return (model_id or "").strip() == MOSS_VG_HUB


def normalize_kokoro_speaker(raw: str | None) -> str | None:
    """Map friendly names (Bella, Nicole, Adam) to Kokoro voice ids; pass through other ids."""
    t = (raw or "").strip()
    if not t:
        return None
    key = t.lower().replace(" ", "_").replace("-", "_")
    if key in _KOKORO_ALIASES:
        return _KOKORO_ALIASES[key]
    return t


def pick_kokoro_speaker(explicit: str | None) -> str:
    """If the user set a speaker, use it; otherwise choose randomly from social presets (shuffle)."""
    n = normalize_kokoro_speaker(explicit)
    if n:
        return n
    return random.choice(KOKORO_SOCIAL_PRESETS)


def kokoro_speaker_for_unhinged_segment(explicit: str | None, segment_index: int) -> str:
    """
    Unhinged multi-segment mode: when no per-character Kokoro id is set, cycle Bella → Nicole → Adam
    (deterministic by segment order). If the user set a speaker, use it for every segment.
    """
    n = normalize_kokoro_speaker(explicit)
    if n:
        return n
    return KOKORO_SOCIAL_PRESETS[segment_index % len(KOKORO_SOCIAL_PRESETS)]


def try_kokoro_tts(
    *,
    model_id: str,
    text: str,
    out_wav: Path,
    speaker: str,
    quant_mode: str | None = None,  # accepted for API symmetry; Kokoro library has no quant controls
) -> bool:
    """
    Synthesize with ``kokoro`` KPipeline (``pip install kokoro``) when the selected voice model is Kokoro-82M.
    """
    if not is_kokoro_repo(model_id) or not (text or "").strip():
        return False
    try:
        from kokoro import KPipeline  # type: ignore[import-not-found]
    except Exception:
        return False
    try:
        import numpy as np
        import soundfile as sf
    except Exception:
        return False
    try:
        pipeline = KPipeline(lang_code="a")
        gen = pipeline(text, voice=speaker)
        chunks: list = []
        sr = 24000
        for _gs, _ps, audio in gen:
            chunks.append(np.asarray(audio, dtype=np.float32))
        if not chunks:
            return False
        merged = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out_wav), merged, int(sr), subtype="PCM_16")
        return out_wav.exists() and out_wav.stat().st_size >= 1024
    except Exception:
        return False


def try_moss_voicegenerator_tts(
    *,
    model_id: str,
    text: str,
    instruction: str,
    out_wav: Path,
    quant_mode: str | None = None,
    cuda_voice_device_index: int | None = None,
) -> bool:
    """
    MOSS-VoiceGenerator: free-form *instruction* (voice design) + *text* (words to speak).
    Requires recent ``transformers`` with ``trust_remote_code`` and a capable GPU/CPU; often several GB VRAM.

    ``quant_mode`` overrides the dtype: ``bf16``/``fp16`` chooses dtype on CUDA;
    ``int8``/``nf4_4bit`` are experimental — falls back to fp16 on failure;
    ``cpu_offload`` forces CPU execution.
    """
    if not is_moss_vg_repo(model_id) or not (text or "").strip():
        return False
    inst = (instruction or "").strip() or DEFAULT_MOSS_INSTRUCTION
    try:
        import importlib.util

        import numpy as np
        import soundfile as sf
        import torch
        from transformers import AutoModel, AutoProcessor
    except Exception:
        return False
    if importlib.util.find_spec("transformers") is None:
        return False

    path = MOSS_VG_HUB
    try:
        qm = (quant_mode or "auto").strip().lower()
        if qm == "cpu_offload":
            device: str = "cpu"
        else:
            from src.util.cuda_capabilities import cuda_device_reported_by_torch

            device = "cuda" if cuda_device_reported_by_torch() else "cpu"
            if device == "cuda" and cuda_voice_device_index is not None:
                try:
                    dv = int(cuda_voice_device_index)
                    torch.cuda.set_device(dv)
                    device = f"cuda:{dv}"
                except Exception:
                    device = "cuda"

        on_cuda = str(device).startswith("cuda")

        if qm == "fp16":
            dtype = torch.float16 if on_cuda else torch.float32
        elif qm == "bf16":
            dtype = torch.bfloat16 if on_cuda else torch.float32
        else:
            dtype = torch.bfloat16 if on_cuda else torch.float32

        def _attn_impl() -> str:
            if on_cuda:
                if importlib.util.find_spec("flash_attn") is not None and dtype in (torch.float16, torch.bfloat16):
                    major, _ = torch.cuda.get_device_capability()
                    if major >= 8:
                        return "flash_attention_2"
                return "sdpa"
            return "eager"

        if on_cuda:
            try:
                torch.backends.cuda.enable_cudnn_sdp(False)  # type: ignore[attr-defined]
            except Exception:
                pass

        processor = AutoProcessor.from_pretrained(
            path,
            trust_remote_code=True,
            normalize_inputs=True,
        )
        processor.audio_tokenizer = processor.audio_tokenizer.to(device)  # type: ignore[union-attr]

        # Experimental: try bnb quant config on CUDA when explicitly requested.
        bnb_cfg = None
        if on_cuda and qm in ("int8", "nf4_4bit"):
            try:
                from transformers import BitsAndBytesConfig as _BnB

                if qm == "nf4_4bit":
                    bnb_cfg = _BnB(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True)
                else:
                    bnb_cfg = _BnB(load_in_8bit=True)
            except Exception:
                bnb_cfg = None

        try:
            if bnb_cfg is not None:
                model = AutoModel.from_pretrained(
                    path,
                    trust_remote_code=True,
                    attn_implementation=_attn_impl(),
                    torch_dtype=dtype,
                    quantization_config=bnb_cfg,
                )
            else:
                raise TypeError("no_bnb")
        except Exception:
            model = AutoModel.from_pretrained(
                path,
                trust_remote_code=True,
                attn_implementation=_attn_impl(),
                torch_dtype=dtype,
            )
        try:
            model = model.to(device)
        except Exception:
            pass
        model.eval()

        umsg = processor.build_user_message(text=text, instruction=inst)
        conv = [[umsg]]
        batch = processor(conv, mode="generation")
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        with torch.no_grad():
            outputs = model.generate(input_ids=input_ids, attention_mask=attention_mask)
        decoded = processor.decode(outputs)
        if not decoded:
            return False
        message = next(iter(decoded))
        audio = message.audio_codes_list[0]
        sr = int(getattr(processor.model_config, "sampling_rate", 24000) or 24000)
        if hasattr(audio, "detach"):
            audio = audio.detach().float().cpu().numpy()
        else:
            audio = np.asarray(audio, dtype=np.float32)
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        # 1D float waveform
        if audio.ndim > 1:
            audio = np.mean(audio, axis=0) if audio.shape[0] < audio.shape[-1] else np.mean(audio, axis=-1)
        sf.write(str(out_wav), audio.astype(np.float32), sr, subtype="PCM_16")
        return out_wav.exists() and out_wav.stat().st_size >= 1024
    except Exception:
        return False
