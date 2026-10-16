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
is_live = False
live_feeder = None

# Auto-next queue. The frontend sends the list a track was picked from with
# /play; when a track ends cleanly, watch_player() starts queue[queue_index + 1]
# itself, so auto-next works with the phone's screen off / page asleep.
queue = []            # [{"id": ..., "title": ...}, ...]
queue_index = -1      # index of the current track in queue, -1 = no queue
queue_source = None   # frontend list name ("history", "liked", "playlist", ...)
auto_next = True
current_track_id = ""

# Lock for player state mutations (play_generation, player_process, paused, loading)
player_lock = threading.Lock()

# Next-track lookahead: url -> resolved metadata dict, so start_playback can
# skip the ~20s yt-dlp resolution when the frontend pre-resolved the track.
preresolve_cache = {}
preresolve_inflight = set()
preresolve_lock = threading.Lock()
