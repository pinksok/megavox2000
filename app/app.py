#!/usr/bin/env python3
"""Headless Music Player - Web Controller using ffplay."""

import subprocess
import os
import threading
import time

from flask import Flask, render_template, request, jsonify, send_from_directory

import state
import services
import service_youtube
import service_spotify
import service_pandora
import json
from player import stop_player, start_playback, toggle_pause_internal, seek_to, _pulse_env
from auth import auth_bp
from library import library_bp
from mpris import mpris_thread_func
from config import VOLUME_FILE, DEFAULT_VOLUME
from wifi_setup import setup_bp, is_setup_mode

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB max request body
app.register_blueprint(auth_bp)
app.register_blueprint(library_bp)
app.register_blueprint(setup_bp)

# Register music services
services.register(service_youtube)
services.register(service_spotify)
services.register(service_pandora)
services.load_active_service()


@app.before_request
def setup_mode_intercept():
    """In setup mode, serve setup page for all non-API requests (captive portal)."""
    if is_setup_mode():
        if request.path.startswith('/setup/') or request.path == '/favicon.svg':
            return None
        return render_template('setup.html')


@app.route("/favicon.svg")
def favicon():
    return send_from_directory(app.root_path, "favicon.svg", mimetype="image/svg+xml")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/play", methods=["POST"])
def play():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400
    url = data.get("url", "")

    # Support playing by track ID (frontend sends {id, title})
    if not url and data.get("id"):
        svc = services.get_service()
        if svc:
            url = svc.build_url(data["id"])

    if not url:
        return jsonify({"error": "No URL provided"})

    stop_player()
    state.last_error = ""
    state.current_title = data.get("title", "")
    state.current_thumbnail = ""
    state.paused = False
    state.loading = True

    t = threading.Thread(target=start_playback, args=(url,), daemon=True)
    t.start()

    return jsonify({"status": "Resolving audio...", "title": data.get("title", url), "thumbnail": ""})


@app.route("/pause", methods=["POST"])
def pause_route():
    toggle_pause_internal()
    if state.player_process and state.player_process.poll() is None:
        status_text = "Paused" if state.paused else "Playing"
        return jsonify({"status": status_text, "paused": state.paused})
    return jsonify({"status": "Nothing playing", "paused": False})


@app.route("/stop", methods=["POST"])
def stop():
    stop_player()
    state.last_error = ""
    state.current_title = ""
    state.current_thumbnail = ""
    state.paused = False
    state.current_duration = 0
    state.playback_start_time = 0
    state.playback_elapsed = 0
    return jsonify({"status": "Stopped"})


@app.route("/seek", methods=["POST"])
def seek():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400
    position = int(data.get("position", 0))
    if seek_to(position):
        return jsonify({"status": "Seeking...", "elapsed": position})
    return jsonify({"error": "Nothing playing"})


@app.route("/volume", methods=["GET"])
def get_volume():
    """Read master sink volume."""
    try:
        result = subprocess.run(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            capture_output=True, text=True, timeout=5, env=_pulse_env(),
        )
        for part in result.stdout.split("/"):
            part = part.strip()
            if part.endswith("%"):
                return jsonify({"volume": int(part[:-1])})
    except Exception:
        pass
    return jsonify({"volume": 100})


@app.route("/volume", methods=["POST"])
def set_volume():
    """Set master sink volume and persist to disk."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400
    vol = data.get("volume", DEFAULT_VOLUME)
    vol = max(0, min(100, int(vol)))
    try:
        subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "{}%".format(vol)],
            timeout=5, env=_pulse_env(),
        )
    except Exception:
        pass
    try:
        with open(VOLUME_FILE, "w") as f:
            json.dump({"volume": vol}, f)
    except Exception:
        pass
    return jsonify({"volume": vol})


@app.route("/status")
def status():
    duration = state.current_duration

    if state.last_error:
        return jsonify({"title": "", "thumbnail": "", "state": "", "error": state.last_error, "paused": state.paused, "elapsed": 0, "duration": 0})

    if state.player_process and state.player_process.poll() is not None:
        return jsonify({"title": "", "thumbnail": "", "state": "Idle", "paused": False, "elapsed": 0, "duration": 0})

    if state.player_process and state.player_process.poll() is None:
        state.loading = False
        play_state = "Paused" if state.paused else "Playing"
    elif state.loading:
        play_state = "Resolving audio..."
    else:
        play_state = "Idle"

    elapsed = state.playback_elapsed
    if state.playback_start_time and not state.paused:
        elapsed += time.time() - state.playback_start_time
    elapsed = min(int(elapsed), duration) if duration else int(elapsed)

    return jsonify({"title": state.current_title, "thumbnail": state.current_thumbnail, "state": play_state, "paused": state.paused, "elapsed": elapsed, "duration": duration})


@app.route("/service", methods=["GET"])
def get_service_route():
    all_svcs = services.get_all_services()
    return jsonify({
        "active": state.active_service,
        "services": [{"name": m.SERVICE_NAME, "display_name": m.SERVICE_DISPLAY_NAME}
                      for m in all_svcs.values()]
    })


@app.route("/service", methods=["POST"])
def set_service_route():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400
    name = data.get("service", "")
    if services.set_active_service(name):
        return jsonify({"status": "Switched to " + name, "active": name})
    return jsonify({"error": "Unknown service: " + name})


def _restore_volume():
    """Restore saved volume on startup, or apply default."""
    vol = DEFAULT_VOLUME
    try:
        with open(VOLUME_FILE, "r") as f:
            vol = json.load(f).get("volume", DEFAULT_VOLUME)
            vol = max(0, min(100, int(vol)))
    except Exception:
        pass
    try:
        subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "{}%".format(vol)],
            timeout=5, env=_pulse_env(),
        )
    except Exception:
        pass


if __name__ == "__main__":
    # Kill any orphaned ffplay processes from a previous crash/restart
    subprocess.run(['killall', '-9', 'ffplay'], capture_output=True)
    _restore_volume()
    # Start MPRIS D-Bus service for BT hardware button support
    mpris_t = threading.Thread(target=mpris_thread_func, daemon=True)
    mpris_t.start()
    app.run(host="0.0.0.0", port=5000)
