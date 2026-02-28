"""Shared mutable playback state.

All playback-related global variables live here so that player.py,
routes, and mpris.py can all import them without circular imports.
Always use attribute access (state.X), never 'from state import X'.
"""

import threading

player_process = None
last_error = ""
loading = False
current_title = ""
current_thumbnail = ""
paused = False
auth_pending = None
active_service = "youtube"
play_generation = 0
current_duration = 0
playback_start_time = 0
playback_elapsed = 0
current_audio_url = ""

# Lock for player state mutations (play_generation, player_process, paused, loading)
player_lock = threading.Lock()
