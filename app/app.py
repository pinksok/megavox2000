#!/usr/bin/env python3
"""Headless Music Player - Web Controller using ffplay."""

import subprocess
import os
import threading
import time

from flask import redirect, Response, Flask, render_template, request, jsonify, send_from_directory

import state
import services
import service_youtube
import service_spotify
import service_pandora
import json
from player import stop_player, start_playback, toggle_pause_internal, seek_to, _pulse_env
from auth import auth_bp
from library import library_bp
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
        # Captive portal detection — redirect OS probes to setup page
        # Windows
        if 'connecttest' in request.host or request.path == '/connecttest.txt':
            return redirect('http://10.42.0.1/')
        if request.path == '/ncsi.txt':
            return redirect('http://10.42.0.1/')
        if 'msftconnecttest' in request.host:
            return redirect('http://10.42.0.1/')
        # Android
        if request.path == '/generate_204' or request.path == '/gen_204':
            return redirect('http://10.42.0.1/')
        if 'connectivitycheck' in request.host:
            return redirect('http://10.42.0.1/')
        # Apple iOS/macOS
        if request.path == '/hotspot-detect.html':
            return Response('<HTML><HEAD><TITLE>MegaVox</TITLE></HEAD><BODY>MegaVox</BODY></HTML>', status=200, content_type='text/html')
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

    # Kill any lingering ffplay that stop_player might have missed
    subprocess.run(['killall', '-9', 'ffplay'], capture_output=True)

    t = threading.Thread(target=start_playback, args=(url,), daemon=True)
    t.start()

    return jsonify({"status": "ACQUIRING SIGNAL...", "title": data.get("title", url), "thumbnail": ""})


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
    if state.is_live:
        return jsonify({"error": "Cannot seek live stream"})
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
        return jsonify({"title": "", "thumbnail": "", "state": "", "error": state.last_error, "paused": state.paused, "elapsed": 0, "duration": 0, "is_live": False})

    if state.player_process and state.player_process.poll() is not None:
        return jsonify({"title": "", "thumbnail": "", "state": "Idle", "paused": False, "elapsed": 0, "duration": 0, "is_live": False})

    if state.player_process and state.player_process.poll() is None:
        state.loading = False
        play_state = "Paused" if state.paused else "Playing"
    elif state.loading:
        play_state = "ACQUIRING SIGNAL..."
    else:
        play_state = "Idle"

    elapsed = state.playback_elapsed
    if state.playback_start_time and not state.paused:
        elapsed += time.time() - state.playback_start_time
    elapsed = min(int(elapsed), duration) if duration else int(elapsed)

    return jsonify({"title": state.current_title, "thumbnail": state.current_thumbnail, "state": play_state, "paused": state.paused, "elapsed": elapsed, "duration": duration, "is_live": state.is_live})


@app.route("/wifi-signal")
def wifi_signal():
    try:
        with open("/proc/net/wireless") as f:
            lines = f.readlines()
        if len(lines) >= 3:
            # Third line has the data: iface | status | quality | level | noise
            parts = lines[2].split()
            level = float(parts[3])  # dBm (negative)
            # Convert dBm to 0-4 bars
            if level >= -45:
                bars = 4
            elif level >= -55:
                bars = 3
            elif level >= -65:
                bars = 2
            elif level >= -75:
                bars = 1
            else:
                bars = 0
            # Get connected SSID
            ssid = ""
            try:
                result = subprocess.run(["iwgetid", "-r"], capture_output=True, text=True, timeout=2)
                ssid = result.stdout.strip()
            except Exception:
                pass
            return jsonify({"bars": bars, "dbm": round(level, 1), "ssid": ssid})
    except Exception:
        pass
    return jsonify({"bars": -1, "dbm": 0})


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


def _auto_resume():
    """Auto-resume the last played track after boot."""
    from history import get_history
    from wifi_setup import is_setup_mode
    time.sleep(10)  # Wait for PulseAudio and network
    if is_setup_mode():
        return
    # Don't resume if something is already playing (e.g. user started a track)
    if state.player_process or state.loading:
        print("[AUTO-RESUME] Skipped — already playing.", flush=True)
        return
    try:
        history = get_history(1)
        tracks = history.get("tracks", [])
        if not tracks:
            return
        track = tracks[0]
        track_id = track.get("id")
        title = track.get("title", "")
        if not track_id:
            return
        svc = services.get_service()
        if not svc:
            return
        url = svc.build_url(track_id)
        # Kill any orphaned ffplay before auto-resume
        subprocess.run(['killall', '-9', 'ffplay'], capture_output=True)
        print("[AUTO-RESUME] Playing: {}".format(title), flush=True)
        stop_player()
        state.current_title = title
        state.loading = True
        start_playback(url)
    except Exception as e:
        print("[AUTO-RESUME] Error: {}".format(e), flush=True)


if __name__ == "__main__":
    # Kill any orphaned ffplay processes from a previous crash/restart
    subprocess.run(['killall', '-9', 'ffplay'], capture_output=True)
    _restore_volume()
    threading.Thread(target=_auto_resume, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
