"""Profile tab attach times with warm imports."""
import os, sys, time
os.environ["AQUADUCT_NO_SPLASH"] = "1"
root = os.path.dirname(os.path.abspath(__file__))
os.chdir(root); sys.path.insert(0, root)

from PyQt6.QtWidgets import QApplication, QTabWidget, QMainWindow
app = QApplication(sys.argv)

# Warm heavy imports
import torch, transformers, diffusers  # noqa
from UI.main_window import MainWindow
from src.settings.ui_settings import load_settings
from src.core.config import get_paths

class Stub:
    pass

win = Stub()
win.settings = load_settings()
win.paths = get_paths()
win.tabs = QTabWidget()
win._model_integrity_by_repo = {}
win._getting_started_dismissed = False
mw = QMainWindow()
win.tabs.setParent(mw)

import UI.main_window as mwmod
attachers = [
    ("run", mwmod.attach_run_tab),
    ("topics", mwmod.attach_topics_tab),
    ("characters", mwmod.attach_characters_tab),
    ("settings", mwmod.attach_settings_tab),
    ("video", mwmod.attach_video_tab),
    ("picture", mwmod.attach_picture_tab),
    ("effects", mwmod.attach_effects_tab),
    ("captions", mwmod.attach_captions_tab),
    ("api", mwmod.attach_api_tab),
    ("branding", mwmod.attach_branding_tab),
    ("tasks", mwmod.attach_tasks_tab),
    ("library", mwmod.attach_library_tab),
    ("my_pc", mwmod.attach_my_pc_tab),
]

for name, fn in attachers:
    t0 = time.perf_counter()
    fn(win)
    print(f"{name}: {time.perf_counter()-t0:.2f}s", flush=True)
