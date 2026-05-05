from __future__ import annotations

import shutil
import traceback
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from src.content.brain import expand_custom_field_text, generate_character_from_preset_llm
from src.content.brain_api import (
    generate_character_from_preset_openai,
)
from src.content.character_presets import CharacterAutoPreset, GeneratedCharacterFields
from src.content.topic_discovery import discover_topics_from_items
from src.content.topic_research_assets import write_topic_research_pack
from src.content.topics import (
    topic_tags_for_mode,
    video_format_writes_topic_research_pack,
)
from src.core.config import AppSettings, get_paths
from src.content.crawler import fetch_latest_items
from src.models.hf_access import ensure_hf_token_in_env, humanize_hf_hub_error
from src.render.artist import generate_images
from src.runtime.api_generation import generate_still_png_bytes
from src.runtime.model_backend import is_api_mode
from src.util.cuda_device_policy import resolve_diffusion_cuda_device_index
from src.util.memory_budget import release_between_stages

from UI.dialogs.auxiliary_progress_dialog import map_llm_on_task_to_overall
from UI.workers.common import (
    _firecrawl_kwargs,
    _reraise_system_interrupt,
)
from debug import dprint


class TopicDiscoverWorker(QThread):
    done = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, settings: AppSettings, *, limit: int = 12, topic_mode: str = "news"):
        super().__init__()
        self.settings = settings
        self.limit = limit
        self.topic_mode = topic_mode

    def run(self) -> None:
        try:
            dprint("topics", "TopicDiscoverWorker", f"limit={self.limit}", f"mode={self.topic_mode}")
            app = self.settings
            items = fetch_latest_items(
                limit=max(5, int(self.limit)),
                topic_tags=topic_tags_for_mode(app, self.topic_mode),
                topic_mode=self.topic_mode,
                topic_discover_only=True,
                **_firecrawl_kwargs(app),
            )
            topics = discover_topics_from_items(items, limit=40, topic_mode=self.topic_mode)
            if video_format_writes_topic_research_pack(self.topic_mode) and items:
                try:
                    pack = write_topic_research_pack(
                        items=items,
                        mode=self.topic_mode,
                        data_dir=get_paths().data_dir,
                    )
                    if pack is not None:
                        dprint("topics", "topic research pack", str(pack))
                except Exception:
                    pass
            self.done.emit(topics)
        except BaseException as e:
            _reraise_system_interrupt(e)
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class TextExpandWorker(QThread):
    """Run ``expand_custom_field_text`` off the GUI thread (loads LLM; can take a while)."""

    progress = pyqtSignal(int, str)  # 0–100, status label
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        model_id: str,
        field_label: str,
        seed: str,
        hf_token: str = "",
        hf_api_enabled: bool = True,
        try_llm_4bit: bool = True,
        app_settings: AppSettings | None = None,
    ) -> None:
        super().__init__()
        self.model_id = str(model_id or "").strip()
        self.field_label = str(field_label or "").strip()
        self.seed = str(seed or "")
        self.hf_token = str(hf_token or "").strip()
        self.hf_api_enabled = bool(hf_api_enabled)
        self.try_llm_4bit = bool(try_llm_4bit)
        self.app_settings = app_settings

    def run(self) -> None:
        try:
            self.progress.emit(0, "Starting…")
            if self.app_settings is not None and is_api_mode(self.app_settings):
                from src.content.brain_api import expand_custom_field_text_openai

                self.progress.emit(12, "API: contacting provider…")
                out = expand_custom_field_text_openai(
                    settings=self.app_settings,
                    field_label=self.field_label,
                    seed=self.seed,
                )
                self.progress.emit(100, "Done")
                self.done.emit(out)
                return
            if not self.model_id:
                self.failed.emit("No script (LLM) model selected in Model tab.")
                return
            ensure_hf_token_in_env(hf_token=self.hf_token, hf_api_enabled=self.hf_api_enabled)

            def _emit_llm(task: str, pct: int, msg: str) -> None:
                self.progress.emit(map_llm_on_task_to_overall(task, pct), msg)

            out = expand_custom_field_text(
                model_id=self.model_id,
                field_label=self.field_label,
                seed=self.seed,
                on_llm_task=_emit_llm,
                try_llm_4bit=self.try_llm_4bit,
                inference_settings=self.app_settings,
            )
            self.progress.emit(100, "Done")
            self.done.emit(out)
        except BaseException as e:
            _reraise_system_interrupt(e)
            friendly = humanize_hf_hub_error(e)
            if friendly:
                self.failed.emit(friendly)
                return
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class TopicGroundingNotesWorker(QThread):
    """Batch-generate per-tag grounding lines via script LLM (local or API mode)."""

    progress = pyqtSignal(int, str)  # 0–100, status label
    batch_done = pyqtSignal(dict)  # {"notes": {norm: note}, "missing": [norm, ...]}
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        model_id: str,
        video_format: str,
        tag_pairs: list[tuple[str, str]],
        sibling_display_labels: list[str],
        seed_notes_by_norm: dict[str, str],
        hf_token: str = "",
        hf_api_enabled: bool = True,
        try_llm_4bit: bool = True,
        app_settings: AppSettings | None = None,
    ) -> None:
        super().__init__()
        self.model_id = str(model_id or "").strip()
        self.video_format = str(video_format or "news").strip()
        self.tag_pairs = list(tag_pairs)
        self.sibling_display_labels = list(sibling_display_labels)
        self.seed_notes_by_norm = dict(seed_notes_by_norm)
        self.hf_token = str(hf_token or "").strip()
        self.hf_api_enabled = bool(hf_api_enabled)
        self.try_llm_4bit = bool(try_llm_4bit)
        self.app_settings = app_settings

    def run(self) -> None:
        try:
            self.progress.emit(0, "Starting…")
            if self.app_settings is not None and is_api_mode(self.app_settings):
                from src.content.brain_api import generate_topic_tag_grounding_notes_openai

                self.progress.emit(12, "API: grounding notes - contacting provider…")
                notes, missing = generate_topic_tag_grounding_notes_openai(
                    settings=self.app_settings,
                    tag_pairs=self.tag_pairs,
                    video_format=self.video_format,
                    sibling_displays=self.sibling_display_labels,
                    seed_notes_by_norm=self.seed_notes_by_norm,
                )
                self.progress.emit(100, "Done")
                self.batch_done.emit({"notes": notes, "missing": list(missing)})
                return
            if not self.model_id:
                self.failed.emit("No script (LLM) model selected in Model tab.")
                return
            ensure_hf_token_in_env(hf_token=self.hf_token, hf_api_enabled=self.hf_api_enabled)
            from src.content.brain import generate_topic_tag_grounding_notes_llm

            def _emit_llm(task: str, pct: int, msg: str) -> None:
                self.progress.emit(map_llm_on_task_to_overall(task, pct), msg)

            notes, missing = generate_topic_tag_grounding_notes_llm(
                model_id=self.model_id,
                tag_pairs=self.tag_pairs,
                video_format=self.video_format,
                sibling_displays=self.sibling_display_labels,
                seed_notes_by_norm=self.seed_notes_by_norm,
                on_llm_task=_emit_llm,
                try_llm_4bit=self.try_llm_4bit,
                inference_settings=self.app_settings,
            )
            self.progress.emit(100, "Done")
            self.batch_done.emit({"notes": notes, "missing": list(missing)})
        except BaseException as e:
            _reraise_system_interrupt(e)
            friendly = humanize_hf_hub_error(e)
            if friendly:
                self.failed.emit(friendly)
                return
            try:
                from src.platform.openai_client import OpenAIRequestError

                if isinstance(e, OpenAIRequestError):
                    self.failed.emit(str(e))
                    return
            except Exception:
                pass
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class CharacterGenerateWorker(QThread):
    """Run ``generate_character_from_preset_llm`` off the GUI thread."""

    progress = pyqtSignal(int, str)
    done = pyqtSignal(object)  # GeneratedCharacterFields
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        model_id: str,
        preset: CharacterAutoPreset,
        extra_notes: str = "",
        try_llm_4bit: bool = True,
        hf_token: str = "",
        hf_api_enabled: bool = True,
        app_settings: AppSettings | None = None,
    ) -> None:
        super().__init__()
        self.model_id = str(model_id or "").strip()
        self.preset = preset
        self.extra_notes = str(extra_notes or "")
        self.try_llm_4bit = bool(try_llm_4bit)
        self.hf_token = str(hf_token or "").strip()
        self.hf_api_enabled = bool(hf_api_enabled)
        self.app_settings = app_settings

    def run(self) -> None:
        try:
            self.progress.emit(0, "Starting…")
            if self.app_settings is not None and is_api_mode(self.app_settings):
                self.progress.emit(14, "API: generating character fields…")
                out = generate_character_from_preset_openai(
                    settings=self.app_settings,
                    preset=self.preset,
                    extra_notes=self.extra_notes,
                    video_format=str(getattr(self.app_settings, "video_format", "") or "") or None,
                )
            else:
                if not self.model_id:
                    self.failed.emit("No script (LLM) model selected in Model tab.")
                    return
                ensure_hf_token_in_env(hf_token=self.hf_token, hf_api_enabled=self.hf_api_enabled)

                def _emit_llm(task: str, pct: int, msg: str) -> None:
                    self.progress.emit(map_llm_on_task_to_overall(task, pct), msg)

                out = generate_character_from_preset_llm(
                    model_id=self.model_id,
                    preset=self.preset,
                    extra_notes=self.extra_notes,
                    on_llm_task=_emit_llm,
                    try_llm_4bit=self.try_llm_4bit,
                    inference_settings=self.app_settings,
                    video_format=str(getattr(self.app_settings, "video_format", "") or "") or None,
                )
            assert isinstance(out, GeneratedCharacterFields)
            self.progress.emit(100, "Done")
            self.done.emit(out)
        except BaseException as e:
            _reraise_system_interrupt(e)
            friendly = humanize_hf_hub_error(e)
            if friendly:
                self.failed.emit(friendly)
                return
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class CharacterPortraitWorker(QThread):
    """Generate a single host portrait with the project image model; saves under data/characters/<id>/portrait.png."""

    progress = pyqtSignal(int, str)
    done = pyqtSignal(str)  # reference_image_rel
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        image_model_id: str,
        character_id: str,
        visual_style: str,
        subject_prefix: str = "",
        allow_nsfw: bool = False,
        steps: int = 4,
        art_style_preset_id: str = "balanced",
        app_settings: AppSettings | None = None,
    ) -> None:
        super().__init__()
        self.image_model_id = str(image_model_id or "").strip()
        self.character_id = str(character_id or "").strip()
        self.visual_style = str(visual_style or "").strip()
        self.subject_prefix = str(subject_prefix or "").strip()
        self.allow_nsfw = bool(allow_nsfw)
        self.steps = max(1, int(steps))
        self.art_style_preset_id = str(art_style_preset_id or "balanced").strip() or "balanced"
        self.app_settings = app_settings

    def run(self) -> None:
        try:
            self.progress.emit(0, "Starting portrait…")
            if not self.character_id:
                self.failed.emit("No character selected.")
                return
            if not self.visual_style.strip():
                self.failed.emit("Fill in Visual style before generating a portrait.")
                return
            if self.app_settings is None or not is_api_mode(self.app_settings):
                if not self.image_model_id:
                    self.failed.emit("No image model selected on the Model tab.")
                    return

            base = get_paths().data_dir / "characters" / self.character_id
            base.mkdir(parents=True, exist_ok=True)
            tmp = base / "_gen_tmp"
            shutil.rmtree(tmp, ignore_errors=True)
            tmp.mkdir(parents=True, exist_ok=True)

            vs_line = self.visual_style.strip()
            sp = self.subject_prefix.strip()
            if sp:
                vs_line = f"{sp}, {vs_line}" if vs_line else sp
            prompt = (
                f"{vs_line}, single character portrait, one clear subject, "
                "looking at camera, sharp focus, vertical 9:16 composition"
            )
            if self.allow_nsfw:
                prompt += (
                    ", adult editorial portrait, tasteful lingerie or implied intimacy optional, "
                    "studio lighting, single consenting adult performer 21 plus, no minors"
                )
            dest = base / "portrait.png"
            if self.app_settings is not None and is_api_mode(self.app_settings):
                self.progress.emit(22, "API: requesting portrait image…")
                png = generate_still_png_bytes(settings=self.app_settings, prompt=prompt)
                dest.write_bytes(png)
                self.progress.emit(92, "Saving portrait…")
            else:
                from src.models.hf_access import ensure_hf_token_in_env as _ensure_hf

                stp = self.app_settings
                _ensure_hf(
                    hf_token=str(getattr(stp, "hf_token", "") or "") if stp is not None else "",
                    hf_api_enabled=bool(getattr(stp, "hf_api_enabled", True)) if stp is not None else True,
                )
                self.progress.emit(6, "Preparing GPU…")
                release_between_stages(
                    "character_portrait_before_image",
                    cuda_device_index=resolve_diffusion_cuda_device_index(self.app_settings),
                    variant="prepare_diffusion",
                )
                self.progress.emit(
                    10,
                    "Loading diffusion / generating (first load may take several minutes)…",
                )

                def _img_prog(pct_in: int, msg: str) -> None:
                    p = float(max(0, min(100, int(pct_in))))
                    v = int(12.0 + 83.0 * (p / 100.0))
                    self.progress.emit(max(12, min(97, v)), msg or "Generating…")

                gen = generate_images(
                    sdxl_turbo_model_id=self.image_model_id,
                    prompts=[prompt],
                    out_dir=tmp,
                    max_images=1,
                    steps=self.steps,
                    allow_nsfw=self.allow_nsfw,
                    on_image_progress=_img_prog,
                    art_style_preset_id=str(getattr(self, "art_style_preset_id", None) or "balanced"),
                    use_style_continuity=False,
                    cuda_device_index=resolve_diffusion_cuda_device_index(self.app_settings),
                    inference_settings=self.app_settings,
                )
                if not gen:
                    self.failed.emit("Image generation returned no files.")
                    return
                src = gen[0].path
                shutil.copy2(src, dest)
            shutil.rmtree(tmp, ignore_errors=True)
            rel = f"characters/{self.character_id}/portrait.png"
            self.progress.emit(100, "Done")
            self.done.emit(rel)
        except BaseException as e:
            _reraise_system_interrupt(e)
            friendly = humanize_hf_hub_error(e)
            if friendly:
                self.failed.emit(friendly)
                return
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")
