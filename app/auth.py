"""Auth routes - delegates to active service's auth adapter."""

import io

import qrcode
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


@auth_bp.route("/auth/qr")
def auth_qr():
    """Generate QR code for the current auth URL."""
    url = request.args.get("url", "")
    if not url:
        return "No URL", 400
    qr = qrcode.make(url, border=2)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")
