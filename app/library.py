"""Library routes - delegates to active service's library adapter."""

import subprocess

from flask import Blueprint, jsonify, request

from services import get_service
from history import get_history, delete_from_history

library_bp = Blueprint("library", __name__)


@library_bp.route("/library/history/delete", methods=["POST"])
def delete_history_track():
    data = request.get_json()
    if not data or not data.get("id"):
        return jsonify({"error": "No track ID"}), 400
    return jsonify(delete_from_history(data["id"]))


@library_bp.route("/library/<source>")
def library(source):
    svc = get_service()
    if not svc:
        return jsonify({"error": "No service configured"})

    if source == "history":
        limit = request.args.get("limit", 20, type=int)
        return jsonify(get_history(limit))

    if not svc.is_authenticated():
        return jsonify({"error": "Not signed in. Please sign in first."})

    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", 20, type=int)

    if source == "search":
        q = request.args.get("q", "")
        if not q:
            return jsonify({"error": "No search query"})
        return jsonify(svc.search(q, limit))

    if source == "playlists":
        return jsonify(svc.get_playlists())

    if source == "playlist_tracks":
        playlist_id = request.args.get("list", "")
        if not playlist_id:
            return jsonify({"error": "No playlist ID"})
        return jsonify(svc.get_playlist_tracks(playlist_id, offset, limit))

    if source == "liked":
        return jsonify(svc.get_liked(offset, limit))

    return jsonify({"error": "Unknown source"})


@library_bp.route("/bluetooth")
def bluetooth_status():
    """Check Bluetooth connection status."""
    try:
        result = subprocess.run(
            ["bluetoothctl", "info"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = result.stdout
        connected = False
        device_name = ""
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("Name:"):
                device_name = line.split(":", 1)[1].strip()
            if line.startswith("Connected:") and "yes" in line.lower():
                connected = True
        if connected and device_name:
            return jsonify({"connected": True, "device_name": device_name})
        return jsonify({"connected": False, "device_name": ""})
    except Exception:
        return jsonify({"connected": False, "device_name": ""})

