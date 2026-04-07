"""Auth routes - delegates to active service's auth adapter."""

import io
import json as json_mod
import os

import qrcode
import qrcode.image.svg
from flask import Blueprint, jsonify, request, send_file

import state
from services import get_service

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/auth/status")
def auth_status():
    svc = get_service()
    if not svc:
        return jsonify({"authenticated": False, "error": "No service configured"})
    return jsonify(svc.auth_status())


@auth_bp.route("/auth/start", methods=["POST"])
def auth_start():
    svc = get_service()
    if not svc:
        return jsonify({"error": "No service configured"})
    result = svc.auth_start()
    if result.get("device_code"):
        state.auth_pending = result
    return jsonify({k: v for k, v in result.items() if k != "device_code"})


@auth_bp.route("/auth/complete", methods=["POST"])
def auth_complete():
    svc = get_service()
    if not svc:
        return jsonify({"error": "No service configured"})
    result = svc.auth_complete()
    if result.get("success"):
        state.auth_pending = None
    return jsonify(result)


@auth_bp.route("/auth/config", methods=["POST"])
def auth_config():
    """Update OAuth credentials from web UI (no SSH needed)."""
    data = request.get_json() or {}
    client_id = (data.get("client_id") or "").strip()
    client_secret = (data.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        return jsonify({"error": "Both client_id and client_secret are required."})

    # Write to oauth_config.json
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oauth_config.json")
    fd = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json_mod.dump({"client_id": client_id, "client_secret": client_secret}, f, indent=4)

    # Reload credentials in the YouTube service module
    import service_youtube
    service_youtube.reload_oauth_config()

    # Clear any stale auth state
    state.auth_pending = None

    return jsonify({"success": True})


@auth_bp.route("/auth/qr")
def auth_qr():
    """Generate QR code for the current auth URL as SVG."""
    url = request.args.get("url", "")
    if not url:
        return "No URL", 400
    factory = qrcode.image.svg.SvgPathImage
    qr = qrcode.make(url, border=2, image_factory=factory)
    buf = io.BytesIO()
    qr.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype="image/svg+xml")
