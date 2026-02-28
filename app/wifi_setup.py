"""Wi-Fi setup Blueprint for TurboVox 2000.

Handles AP mode detection, network scanning, and Wi-Fi connection
for first-time setup / captive portal onboarding.
"""

import subprocess
import threading
import time
from flask import Blueprint, jsonify, request, render_template

setup_bp = Blueprint("setup", __name__)

SETUP_MODE_FILE = "/tmp/turbovox-mode"
HOTSPOT_CON_NAME = "TurboVox2000-Setup"
HOTSPOT_SSID = "TurboVox2000-Setup"

# Connection state (shared across threads)
_connection_state = {"status": "idle", "error": "", "ssid": "", "ip": ""}
_connection_lock = threading.Lock()


def get_mode():
    """Read current mode from state file."""
    try:
        with open(SETUP_MODE_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        return "client"


def is_setup_mode():
    """Check if we're in AP/setup mode."""
    return get_mode() == "ap"


def _nmcli(*args):
    """Run nmcli command, return (stdout, stderr, returncode)."""
    cmd = ["sudo", "nmcli"] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "Timeout", 1


def scan_networks():
    """Scan for available Wi-Fi networks."""
    # Force a rescan
    subprocess.run(["sudo", "nmcli", "device", "wifi", "rescan"],
                   capture_output=True, timeout=10)
    time.sleep(2)

    stdout, _, rc = _nmcli("-t", "-f", "SSID,SIGNAL,SECURITY",
                           "device", "wifi", "list")
    if rc != 0:
        return []

    networks = {}
    for line in stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[0]:
            ssid = parts[0]
            # Skip our own hotspot
            if ssid == HOTSPOT_SSID:
                continue
            try:
                signal = int(parts[1])
            except ValueError:
                signal = 0
            security = parts[2] if parts[2] else "Open"
            # Keep strongest signal per SSID
            if ssid not in networks or signal > networks[ssid]["signal"]:
                networks[ssid] = {
                    "ssid": ssid,
                    "signal": signal,
                    "security": security
                }

    return sorted(networks.values(), key=lambda x: x["signal"], reverse=True)


def _write_mode(mode):
    """Write mode to state file."""
    try:
        with open(SETUP_MODE_FILE, "w") as f:
            f.write(mode)
    except Exception:
        pass


def _get_ip():
    """Get current IP address of wlan0."""
    stdout, _, _ = _nmcli("-t", "-f", "IP4.ADDRESS", "device", "show", "wlan0")
    for line in stdout.splitlines():
        if ":" in line:
            addr = line.split(":", 1)[1].strip()
            if "/" in addr:
                return addr.split("/")[0]
            return addr
    return ""


def _connect_worker(ssid, password):
    """Background thread: stop AP, connect to network, handle failure."""
    global _connection_state
    with _connection_lock:
        _connection_state = {"status": "connecting", "ssid": ssid, "error": "", "ip": ""}

    # Stop AP
    _nmcli("connection", "down", HOTSPOT_CON_NAME)
    time.sleep(2)

    # Try to connect
    cmd = ["sudo", "nmcli", "device", "wifi", "connect", ssid, "ifname", "wlan0"]
    if password:
        cmd += ["password", password]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        result = None

    if result and result.returncode == 0:
        # Wait for IP assignment
        time.sleep(3)
        ip = _get_ip()
        _write_mode("client")
        with _connection_lock:
            _connection_state = {"status": "connected", "ssid": ssid, "error": "", "ip": ip}
    else:
        error = ""
        if result:
            error = result.stderr.strip() or "Connection failed"
        else:
            error = "Connection timed out"
        # Restart AP for retry
        _nmcli("device", "wifi", "hotspot", "ifname", "wlan0",
               "con-name", HOTSPOT_CON_NAME, "ssid", HOTSPOT_SSID, "band", "bg")
        _write_mode("ap")
        with _connection_lock:
            _connection_state = {"status": "failed", "ssid": ssid, "error": error, "ip": ""}


# --- Routes ---

@setup_bp.route("/setup/status")
def setup_status():
    mode = get_mode()
    ip = _get_ip() if mode == "client" else "10.42.0.1"
    return jsonify({"mode": mode, "ip": ip})


@setup_bp.route("/setup/scan")
def setup_scan():
    if not is_setup_mode():
        return jsonify({"error": "Not in setup mode"}), 403
    networks = scan_networks()
    return jsonify({"networks": networks})


@setup_bp.route("/setup/connect", methods=["POST"])
def setup_connect():
    if not is_setup_mode():
        return jsonify({"error": "Not in setup mode"}), 403
    data = request.get_json()
    if not data or not data.get("ssid"):
        return jsonify({"error": "SSID required"}), 400

    ssid = data["ssid"]
    password = data.get("password", "")

    t = threading.Thread(target=_connect_worker, args=(ssid, password), daemon=True)
    t.start()

    return jsonify({"status": "connecting", "ssid": ssid})


@setup_bp.route("/setup/result")
def setup_result():
    with _connection_lock:
        return jsonify(_connection_state.copy())
