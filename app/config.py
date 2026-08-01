"""Configuration constants."""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_FILE = "/tmp/megavox2000-debug.log"
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
HISTORY_MAX = 200
VOLUME_FILE = os.path.join(BASE_DIR, "volume.json")
DEFAULT_VOLUME = 25
SETUP_MODE_FILE = "/tmp/megavox-mode"

# Netscape-format cookie jar for yt-dlp (optional). When present, it is passed
# to every yt-dlp invocation so YouTube's "confirm you're not a bot" check can
# be satisfied with a logged-in Google account's cookies. Gitignored.
COOKIES_FILE = os.path.join(BASE_DIR, "cookies.txt")
