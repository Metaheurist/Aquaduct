"""Tab builders attach widgets to MainWindow."""

from UI.tabs.api_tab import attach_api_tab
from UI.tabs.characters_tab import attach_characters_tab
from UI.tabs.tasks_tab import attach_tasks_tab
from UI.tabs.branding_tab import attach_branding_tab
from UI.tabs.captions_tab import attach_captions_tab
from UI.tabs.my_pc_tab import attach_my_pc_tab
from UI.tabs.run_tab import attach_run_tab
from UI.tabs.settings_tab import attach_settings_tab
from UI.tabs.topics_tab import attach_topics_tab
from UI.tabs.video_tab import attach_video_tab

__all__ = [
    "attach_characters_tab",
    "attach_run_tab",
    "attach_topics_tab",
    "attach_video_tab",
    "attach_captions_tab",
    "attach_branding_tab",
    "attach_api_tab",
    "attach_settings_tab",
    "attach_my_pc_tab",
    "attach_tasks_tab",
]
