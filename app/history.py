"""Local playback history management."""

import os
import json as json_mod
import time
import tempfile
import threading

import config

_history_lock = threading.Lock()


def log_to_history(track_id, title, thumbnail):
    """Log a played track to local history file (atomic write)."""
    entry = {
        "id": track_id,
        "title": title,
        "thumbnail": thumbnail,
        "played_at": int(time.time()),
    }
    with _history_lock:
        try:
            history = []
            if os.path.exists(config.HISTORY_FILE):
                with open(config.HISTORY_FILE) as f:
                    history = json_mod.load(f)
            # Remove duplicate if same track was played recently
            history = [h for h in history if h.get("id") != track_id]
            # Prepend new entry (most recent first)
            history.insert(0, entry)
            # Trim to max size
            history = history[:config.HISTORY_MAX]
            # Atomic write: write to temp file then rename
            dir_name = os.path.dirname(config.HISTORY_FILE)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json_mod.dump(history, f)
                os.replace(tmp_path, config.HISTORY_FILE)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                raise
        except Exception as e:
            print("[HISTORY] Error saving: {}".format(e), flush=True)


def delete_from_history(track_id):
    """Delete a track from local history by ID."""
    with _history_lock:
        try:
            if not os.path.exists(config.HISTORY_FILE):
                return {"success": True}
            with open(config.HISTORY_FILE) as f:
                history = json_mod.load(f)
            history = [h for h in history if h.get("id") != track_id]
            dir_name = os.path.dirname(config.HISTORY_FILE)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json_mod.dump(history, f)
                os.replace(tmp_path, config.HISTORY_FILE)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                raise
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}


def get_history(limit=20):
    """Fetch local playback history."""
    with _history_lock:
        try:
            if not os.path.exists(config.HISTORY_FILE):
                return {"tracks": [], "has_more": False}
            with open(config.HISTORY_FILE) as f:
                history = json_mod.load(f)
            tracks = history[:limit]
            return {"tracks": tracks, "has_more": len(history) > limit}
        except Exception as e:
            return {"error": str(e)}
