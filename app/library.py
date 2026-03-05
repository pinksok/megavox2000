"""Library routes - delegates to active service's library adapter."""

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

