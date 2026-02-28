"""Configuration constants."""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_FILE = "/tmp/turbovox2000-debug.log"
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
HISTORY_MAX = 200
VOLUME_FILE = os.path.join(BASE_DIR, "volume.json")
DEFAULT_VOLUME = 25
SETUP_MODE_FILE = "/tmp/turbovox-mode"
