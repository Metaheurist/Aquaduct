"""
In-app help: topics on the left, slide-style pages on the right (prev/next).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from UI.frameless_dialog import FramelessDialog
from UI.title_bar_outline_button import styled_outline_button


class _Topic:
    __slots__ = ("topic_id", "label", "slides")

    def __init__(self, *, topic_id: str, label: str, slides: list[tuple[str, str]]) -> None:
        self.topic_id = topic_id
        self.label = label
        self.slides = slides  # (slide_title, body_text)


# Topics and slides: keep titles short; body text is plain (markdown-style ** stripped at display).
TUTORIAL_TOPICS: list[_Topic] = [
    _Topic(
        topic_id="welcome",
        label="Welcome",
        slides=[
            (
                "What Aquaduct does",
                "Aquaduct builds short videos end-to-end: it can pull headlines and your topic tags, "
                "run a local (or API) script model to write narration, synthesize voice, generate images "
                "or motion clips with diffusion, then mux audio and captions into a final MP4.\n\n"
                "Outputs go under your app data folder: videos/ for finished projects (final.mp4, script, "
                "meta.json, assets/), and runs/ for per-run workspace files. Models and settings live "
                "beside them in .Aquaduct_data/.",
            ),
            (
                "Title bar & saving",
                "Save — writes every tab’s settings to ui_settings.json (same as Run → Save settings).\n\n"
                "Resource graph — live CPU, RAM, and GPU memory for this process (about once per second).\n\n"
                "Help — opens this window any time.\n\n"
                "Drag the top bar to move the window. The app uses a fixed width; height follows the active tab.",
            ),
            (
                "Small UX details",
                "Scrolling with the mouse wheel moves the page, not combo boxes or number fields — "
                "those only change when you click or use the keyboard. That avoids accidental edits while scrolling.\n\n"
                "On first launch you may be asked for a Hugging Face token (optional but helps downloads and gated models). "
                "This tutorial can appear after that prompt; closing it once records that you’ve seen it.",
            ),
        ],
    ),
    _Topic(
        topic_id="run",
        label="Run & pipeline",
        slides=[
            (
                "Videos to generate & queue",
                "Each unit is one full pipeline run = one output video folder. Set N greater than 1 to queue "
                "multiple independent runs. The first starts immediately; the rest wait in FIFO order.\n\n"
                "You can click Run again while a job is running — new clicks append to the queue. Stop cancels "
                "the current job and clears queued pipeline runs. Each queued row keeps the settings from "
                "when you clicked.",
            ),
            (
                "Preset vs Custom content",
                "Preset uses your per-format topic tags plus the news/headline cache (behavior depends on "
                "video format). Custom uses your multiline instructions: the script model expands them into a "
                "brief, then writes the full script (two LLM passes — slower than Preset). Custom does not "
                "pick headlines from the cache; tags still help hashtags when relevant.",
            ),
            (
                "Format, personality, character",
                "Video format (News, Cartoon, Explainer, Cartoon unhinged, Creepypasta) selects which topic list and "
                "crawler behavior apply, together with the Topics tab.\n\n"
                "Personality biases tone. Character (optional) ties voice and visuals to a profile from the "
                "Characters tab.",
            ),
            (
                "Preview, storyboard & Tasks",
                "Preview drafts a script package without a full render. Storyboard preview builds a visual "
                "grid plan. Progress for pipeline, preview, and storyboard appears on the Tasks tab with "
                "stage and percent.\n\n"
                "Pause waits between major steps (not mid-GPU). Stop cancels at the next safe checkpoint.",
            ),
        ],
    ),
    _Topic(
        topic_id="topics_chars",
        label="Topics & Characters",
        slides=[
            (
                "Topics — tags per format",
                "The mode selector matches video formats. Each mode has its own tag list stored in settings. "
                "Tags bias crawling and scripting for that format only.\n\n"
                "Use the brain icon on a tag line to expand or improve it with the same Script (LLM) model "
                "chosen on the Model tab.",
            ),
            (
                "Discover",
                "Discover suggests new lines from the web. News/Explainer lean headline-style; Cartoon/Unhinged "
                "use Firecrawl (enable it on the API tab with a key). Approved lines join that mode’s list.\n\n"
                "Cartoon/Unhinged Discover can save a research pack under data/topic_research/ for later "
                "use when you enable story web context on the Video tab.",
            ),
            (
                "Characters",
                "Create profiles (identity, look, negatives, voice). They’re stored in data/characters.json. "
                "Generate with LLM fills fields from presets using your script model.\n\n"
                "If ElevenLabs is enabled on the API tab, you can assign a cloud voice to a character.",
            ),
        ],
    ),
    _Topic(
        topic_id="models",
        label="Models & storage",
        slides=[
            (
                "The four model roles",
                "Script (LLM) — writes and refines the script; also powers brain-expand on Topics and Characters.\n\n"
                "Image — still frames, slideshow, and Pro keyframes for image-to-video models.\n\n"
                "Video — motion clips or Pro segments: text-to-video models animate prompts; img2vid models "
                "use keyframes from the Image model.\n\n"
                "Voice — TTS for narration (local Kokoro-style repos or API routes in API mode).",
            ),
            (
                "Local vs API execution",
                "Local — Hugging Face weights under your models folder, downloads, verify checksums, Auto-fit "
                "for this PC, VRAM fit badges.\n\n"
                "API — hides local download UI and shows Generation APIs (OpenAI, Replicate, etc.) with keys; "
                "same panel is shared with the API tab. Pick providers per role in settings.",
            ),
            (
                "Downloads, verify, dependencies",
                "Download menu: per-role download, all voices, all selected, full curated list, import folder, "
                "verify checksums against the Hub, check/install Python deps with a live log.\n\n"
                "Badges show on-disk size, verified state, or problems. Clear data (Model tab) wipes local app "
                "outputs and default models path — read the warning if you use an external models folder.",
            ),
            (
                "Model files location",
                "Default stores snapshots under .Aquaduct_data/models. External points to another folder for "
                "large disks or shared libraries — set path, Apply, and use Detect to list snapshots.\n\n"
                "Title-bar Save persists storage mode with everything else.",
            ),
        ],
    ),
    _Topic(
        topic_id="video",
        label="Video & output",
        slides=[
            (
                "Platform templates",
                "Tiles are like graphics presets: each applies resolution, FPS, micro-scene bounds, bitrate, "
                "images per video, motion scene counts/timing, and Pro fields. Custom means you changed numbers "
                "after picking a tile.\n\n"
                "Resolution and FPS drive the final frame size and encode.",
            ),
            (
                "Slideshow vs motion & Pro",
                "Slideshow stitches still images with timing from micro-scene min/max. Motion mode uses the "
                "Video model for clips when slideshow is off.\n\n"
                "Pro mode (slideshow off) splits the script into scenes. Text-to-video models render scenes "
                "directly; Stable Video Diffusion–style models use Image-generated keyframes first.",
            ),
            (
                "Quality & story options",
                "Prefer GPU, topic quality, fetch article text, and prompt conditioning tune behavior.\n\n"
                "Story pipeline options: multi-stage script review, Firecrawl web context, reference images "
                "for img2img — need API keys where noted. Cartoon/Unhinged can merge Discover research into context.",
            ),
            (
                "Advanced on Video tab",
                "Optional background music path, clear news URL/title cache, NSFW allow (disables diffusion "
                "safety checker — use responsibly).\n\n"
                "Effects tab: transitions, motion strength, audio polish, SFX, ducking. Captions tab: word "
                "captions and Key facts card (News/Explainer only for the facts overlay).",
            ),
        ],
    ),
    _Topic(
        topic_id="tasks_library",
        label="Tasks & Library",
        slides=[
            (
                "Tasks tab",
                "The tab badge shows a count while pipeline, preview, storyboard, or upload workers run, "
                "or when runs are queued — each queued pipeline appears as its own row.\n\n"
                "Finished renders list from upload_tasks.json: open folder, play final.mp4, copy caption, "
                "mark posted, upload to TikTok or YouTube when configured.",
            ),
            (
                "Library tab",
                "Finished videos lists folders under videos/ that contain final.mp4, with title from meta.json, "
                "dates, and file size. Run workspaces lists runs/ subfolders (intermediate assets).\n\n"
                "Refresh rescans; opening the tab or completing a run updates lists. Open roots, folders, "
                "assets, or play from the toolbar and row actions.",
            ),
        ],
    ),
    _Topic(
        topic_id="api_social",
        label="API & uploads",
        slides=[
            (
                "Keys: HF, Firecrawl, ElevenLabs",
                "Hugging Face token — optional; helps size checks, gated models, and downloads.\n\n"
                "Firecrawl — enable with API key for Discover, article text, and story web context.\n\n"
                "ElevenLabs — optional cloud TTS when enabled and a character selects an ElevenLabs voice.",
            ),
            (
                "Generation APIs (API mode)",
                "When Model execution is API, configure OpenAI-compatible hosts, Replicate, and voice providers "
                "in the Generation APIs block (same controls as the API tab). Environment variables can override "
                "saved keys where documented.",
            ),
            (
                "TikTok & YouTube",
                "Each platform has its own enable, OAuth fields, and optional auto-upload after render. "
                "Configure redirects and ports to match your developer app. Uploads start from the Tasks row "
                "actions when connected.",
            ),
        ],
    ),
    _Topic(
        topic_id="branding",
        label="Branding",
        slides=[
            (
                "Branding tab",
                "Optional palette overrides: pick a preset or Custom and edit hex colors for background, "
                "panels, text, accents, and danger. Watermark: optional logo path, opacity, scale, corner.\n\n"
                "Video style can bias prompts and captions toward your palette when enabled.",
            ),
        ],
    ),
    _Topic(
        topic_id="my_pc",
        label="My PC & help",
        slides=[
            (
                "My PC tab",
                "Shows CPU, RAM, GPU, and VRAM at a glance plus short guidance. Model rows on the Model tab "
                "include fit badges (Excellent / OK / Risky / etc.) from simple VRAM heuristics — not a guarantee, "
                "but useful when choosing weights.\n\n"
                "Auto-fit on the Model tab re-picks script, image, video, and voice models for the detected hardware.",
            ),
            (
                "This help window",
                "Open anytime with ? in the title bar. Topics are on the left; use Previous and Next to move "
                "through slides.\n\n"
                "The first-run tutorial opens once automatically if you haven’t completed it (stored as "
                "tutorial_completed in ui_settings.json). To see it again, set that field to false or start "
                "from a clean app data directory.",
            ),
        ],
    ),
]


class TutorialDialog(FramelessDialog):
    """Modal help window: topic list + slide stack with prev/next."""

    def __init__(
        self,
        parent=None,
        *,
        start_topic_id: str | None = None,
        start_slide: int = 0,
    ) -> None:
        super().__init__(parent, title="Help — tutorials")
        self.setMinimumSize(920, 520)
        self.resize(960, 540)

        self._topics = TUTORIAL_TOPICS
        self._topic_index = 0
        self._slide_index = 0
        self._updating_topic_list = False

        body = self.body_layout
        root = QHBoxLayout()
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        self._list = QListWidget()
        self._list.setObjectName("tutorialTopicList")
        self._list.setFixedWidth(220)
        self._list.setSpacing(4)
        for t in self._topics:
            item = QListWidgetItem(t.label)
            item.setData(Qt.ItemDataRole.UserRole, t.topic_id)
            self._list.addItem(item)
        self._list.currentRowChanged.connect(self._on_topic_row_changed)
        root.addWidget(self._list, 0)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet("color: #2E2E38; max-width: 2px;")
        root.addWidget(divider)

        right = QVBoxLayout()
        right.setSpacing(10)
        self._slide_title = QLabel("")
        self._slide_title.setWordWrap(True)
        self._slide_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #E8E8EE;")
        right.addWidget(self._slide_title)

        self._body = QTextEdit()
        self._body.setReadOnly(True)
        self._body.setFrameShape(QFrame.Shape.NoFrame)
        self._body.setStyleSheet(
            "QTextEdit { background-color: #14141A; color: #C8C8D4; font-size: 13px; "
            "padding: 10px; border-radius: 8px; border: 1px solid #2A2A34; }"
        )
        self._body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right.addWidget(self._body, 1)

        nav = QHBoxLayout()
        nav.setSpacing(10)
        self._counter = QLabel("")
        self._counter.setStyleSheet("color: #8A96A3; font-size: 12px;")
        nav.addWidget(self._counter)

        nav.addStretch(1)

        self._prev_btn = styled_outline_button("◀  Previous", "muted_icon", min_width=120)
        self._prev_btn.clicked.connect(self._prev_slide)
        nav.addWidget(self._prev_btn)

        self._next_btn = styled_outline_button("Next  ▶", "accent_icon", min_width=120)
        self._next_btn.clicked.connect(self._next_slide)
        nav.addWidget(self._next_btn)

        done = styled_outline_button("Close", "accent_icon", min_width=96)
        done.clicked.connect(self.accept)
        nav.addWidget(done)

        right.addLayout(nav)

        wrap = QWidget()
        wrap_l = QVBoxLayout(wrap)
        wrap_l.setContentsMargins(12, 0, 0, 0)
        wrap_l.addLayout(right)
        root.addWidget(wrap, 1)

        body.addLayout(root)

        self._list.setCurrentRow(0)
        self._sync_slide()
        if start_topic_id:
            self.go_to_topic(start_topic_id, start_slide)

    def go_to_topic(self, topic_id: str, slide: int = 0) -> None:
        """Select a topic and slide by ``topic_id`` (see TUTORIAL_TOPICS). Unknown ids are ignored."""
        for i, t in enumerate(self._topics):
            if t.topic_id != topic_id:
                continue
            self._topic_index = i
            slides = t.slides
            mx = max(0, len(slides) - 1) if slides else 0
            self._slide_index = max(0, min(mx, slide))
            self._updating_topic_list = True
            try:
                self._list.setCurrentRow(i)
            finally:
                self._updating_topic_list = False
            self._sync_slide()
            return

    def _current_topic(self) -> _Topic:
        return self._topics[max(0, min(len(self._topics) - 1, self._topic_index))]

    def _on_topic_row_changed(self, row: int) -> None:
        if self._updating_topic_list or row < 0:
            return
        self._topic_index = row
        self._slide_index = 0
        self._sync_slide()

    def _sync_slide(self) -> None:
        topic = self._current_topic()
        slides = topic.slides
        if not slides:
            self._slide_title.setText(topic.label)
            self._body.setPlainText("")
            self._counter.setText("")
            self._prev_btn.setEnabled(False)
            self._next_btn.setEnabled(False)
            return

        self._slide_index = max(0, min(len(slides) - 1, self._slide_index))
        title, text = slides[self._slide_index]
        self._slide_title.setText(title)
        self._body.setPlainText(text.replace("**", ""))
        n = len(slides)
        self._counter.setText(f"Slide {self._slide_index + 1} of {n} — {topic.label}")

        can_prev = self._slide_index > 0 or self._topic_index > 0
        self._prev_btn.setEnabled(can_prev)
        last_topic = self._topic_index >= len(self._topics) - 1
        last_slide = self._slide_index >= n - 1
        self._next_btn.setEnabled(not (last_topic and last_slide))

    def _prev_slide(self) -> None:
        if self._slide_index > 0:
            self._slide_index -= 1
        elif self._topic_index > 0:
            self._topic_index -= 1
            prev_slides = self._topics[self._topic_index].slides
            self._slide_index = max(0, len(prev_slides) - 1)
            self._updating_topic_list = True
            try:
                self._list.setCurrentRow(self._topic_index)
            finally:
                self._updating_topic_list = False
        self._sync_slide()

    def _next_slide(self) -> None:
        topic = self._current_topic()
        slides = topic.slides
        if self._slide_index < len(slides) - 1:
            self._slide_index += 1
        elif self._topic_index < len(self._topics) - 1:
            self._topic_index += 1
            self._slide_index = 0
            self._updating_topic_list = True
            try:
                self._list.setCurrentRow(self._topic_index)
            finally:
                self._updating_topic_list = False
        self._sync_slide()
