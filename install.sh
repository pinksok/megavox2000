#!/bin/bash
set -e

# MegaVox 2000 - Installation Script
# Run on a fresh Raspberry Pi OS Lite (Bookworm or later)
# Usage: sudo bash install.sh

echo ""
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║              MegaVox 2000 Installer              ║"
echo "  ║   MEGA BASS DIGITAL XBS PROCESSING SYSTEM        ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo ""

# --- Validate environment ---
if [ "$(id -u)" -ne 0 ]; then
    echo "Error: Run with sudo (e.g., sudo bash install.sh)"
    exit 1
fi

# Detect the real user (who invoked sudo)
REAL_USER="${SUDO_USER:-pi}"
REAL_HOME=$(eval echo "~$REAL_USER")
REAL_UID=$(id -u "$REAL_USER")
INSTALL_DIR="$REAL_HOME/megavox2000"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "  User:      $REAL_USER (UID $REAL_UID)"
echo "  Install:   $INSTALL_DIR"
echo "  Source:    $SCRIPT_DIR"
echo ""

# --- Step 1: System packages ---
echo "[1/8] Installing system packages..."
apt-get update -qq
apt-get install -y -qq \
    python3-pip \
    python3-flask \
    python3-dbus \
    python3-gi \
    python3-requests \
    ffmpeg \
    pipewire \
    pipewire-pulse \
    wireplumber \
    pulseaudio-utils \
    bluetooth \
    bluez-tools \
    iptables \
    nodejs \
    quickjs \
    network-manager \
    2>/dev/null

echo "  Done."

# --- Step 2: pip packages ---
echo "[2/8] Installing Python packages..."
# yt-dlp[default] pulls in yt-dlp-ejs, the challenge-solver script distribution
# YouTube now requires ("n challenge"). Paired with the quickjs runtime above,
# this lets yt-dlp resolve audio URLs. Without it, only image formats resolve
# and playback fails with "Requested format is not available".
pip3 install --break-system-packages "yt-dlp[default]" qrcode ytmusicapi 2>/dev/null
echo "  Done."

# --- Step 2b: Node.js 22 (fast JS challenge runtime) ---
# yt-dlp needs a JS runtime to solve YouTube's "n challenge". quickjs works but
# interprets the challenge in ~60-80s per track on a Pi 3; Node's V8 JIT does it
# in seconds. Debian ships Node 20 (< yt-dlp's required 22), so install the
# official-source armv6l build from unofficial-builds.nodejs.org (runs on armv7).
NODE_VERSION="v22.23.2"
if ! /usr/local/bin/node --version 2>/dev/null | grep -q "^v2[2-9]"; then
    echo "[2b/8] Installing Node.js $NODE_VERSION (fast yt-dlp challenge solver)..."
    NODE_TAR="node-$NODE_VERSION-linux-armv6l.tar.xz"
    if curl -fsSLo "/tmp/$NODE_TAR" \
        "https://unofficial-builds.nodejs.org/download/release/$NODE_VERSION/$NODE_TAR"; then
        tar -xJf "/tmp/$NODE_TAR" -C /opt
        ln -sf "/opt/node-$NODE_VERSION-linux-armv6l/bin/node" /usr/local/bin/node
        rm -f "/tmp/$NODE_TAR"
        echo "  Done ($(/usr/local/bin/node --version))."
    else
        echo "  WARNING: Node download failed -- playback will fall back to quickjs (slow)."
    fi
fi

# --- Step 3: Copy application files ---
echo "[3/8] Installing application files..."
if [ "$SCRIPT_DIR" = "$INSTALL_DIR" ]; then
    echo "  Running from install directory, skipping copy."
else
    mkdir -p "$INSTALL_DIR/app/templates"
    cp "$SCRIPT_DIR/app/"*.py "$INSTALL_DIR/app/"
    cp "$SCRIPT_DIR/app/favicon.svg" "$INSTALL_DIR/app/"
    cp "$SCRIPT_DIR/app/oauth_config.json.example" "$INSTALL_DIR/app/"
    cp "$SCRIPT_DIR/app/templates/"*.html "$INSTALL_DIR/app/templates/"

    # Copy oauth_config.json if it exists in source (for image building)
    if [ -f "$SCRIPT_DIR/app/oauth_config.json" ]; then
        cp "$SCRIPT_DIR/app/oauth_config.json" "$INSTALL_DIR/app/"
        chmod 600 "$INSTALL_DIR/app/oauth_config.json"
    fi
fi

chown -R "$REAL_USER:$REAL_USER" "$INSTALL_DIR"
echo "  Done."

# --- Step 4: OAuth credentials check ---
echo "[4/8] Checking OAuth configuration..."
if [ -f "$INSTALL_DIR/app/oauth_config.json" ]; then
    echo "  OAuth credentials found."
else
    echo ""
    echo "  *** OAuth credentials not found ***"
    echo "  To use YouTube Music, create:"
    echo "    $INSTALL_DIR/app/oauth_config.json"
    echo "  with contents:"
    echo '    {"client_id": "YOUR_ID", "client_secret": "YOUR_SECRET"}'
    echo "  See README.md for Google Cloud Project setup instructions."
    echo ""
fi

# --- Step 4b: YouTube cookies check ---
# yt-dlp now hits YouTube's "confirm you're not a bot" wall without logged-in
# cookies. app/player.py auto-uses app/cookies.txt if present. This file is
# device-specific (exported from a browser) and is never shipped -- warn if absent.
if [ ! -f "$INSTALL_DIR/app/cookies.txt" ]; then
    echo ""
    echo "  *** YouTube cookies not found ***"
    echo "  Playback needs a browser-exported cookies.txt (Netscape format)."
    echo "  Export youtube.com cookies (logged in) and copy to:"
    echo "    $INSTALL_DIR/app/cookies.txt"
    echo "  See README.md 'YouTube cookies' for the export steps."
    echo ""
fi

# --- Step 5: Set hostname ---
echo "[5/8] Setting hostname to 'mega'..."
hostnamectl set-hostname mega
if grep -q "127.0.1.1" /etc/hosts; then
    sed -i 's/127\.0\.1\.1.*/127.0.1.1\tmega/' /etc/hosts
else
    echo "127.0.1.1	mega" >> /etc/hosts
fi
echo "  Done."

# --- Step 6: Install user service (megavox2000.service) ---
echo "[6/8] Installing user service..."
USER_SERVICE_DIR="$REAL_HOME/.config/systemd/user"
mkdir -p "$USER_SERVICE_DIR"

# Generate service file with correct paths and UID
sed -e "s|INSTALL_DIR_PLACEHOLDER|$INSTALL_DIR|g" \
    -e "s|INSTALL_UID_PLACEHOLDER|$REAL_UID|g" \
    "$SCRIPT_DIR/system/megavox2000.service" > "$USER_SERVICE_DIR/megavox2000.service"

chown -R "$REAL_USER:$REAL_USER" "$REAL_HOME/.config"

# Enable lingering so user services start at boot without login
loginctl enable-linger "$REAL_USER"

# Reload and enable (needs user's runtime dir)
sudo -u "$REAL_USER" XDG_RUNTIME_DIR="/run/user/$REAL_UID" \
    systemctl --user daemon-reload
sudo -u "$REAL_USER" XDG_RUNTIME_DIR="/run/user/$REAL_UID" \
    systemctl --user enable megavox2000.service
echo "  Done."

# --- Step 7: Install boot service (megavox-setup.service) ---
echo "[7/8] Installing boot service..."

# Copy boot script and set the user
cp "$SCRIPT_DIR/system/megavox-boot.sh" "$INSTALL_DIR/megavox-boot.sh"
# Strip CRLF line endings. If the repo was cloned/edited on Windows the script
# can carry \r, which makes the kernel read the shebang as "/bin/bash\r" and the
# boot service dies with status=203/EXEC ("No such file or directory") on every
# boot -- so the iptables 80->5000 redirect never installs and http://mega.local
# is unreachable while music still plays.
sed -i 's/\r$//' "$INSTALL_DIR/megavox-boot.sh"
chmod +x "$INSTALL_DIR/megavox-boot.sh"
sed -i "s|^APP_USER=.*|APP_USER=\"$REAL_USER\"|" "$INSTALL_DIR/megavox-boot.sh"

# Generate system service with correct paths (strip any CRLF from the template)
sed -e "s|INSTALL_DIR_PLACEHOLDER|$INSTALL_DIR|g" -e 's/\r$//' \
    "$SCRIPT_DIR/system/megavox-setup.service" > /etc/systemd/system/megavox-setup.service

# Captive portal DNS config for AP mode
mkdir -p /etc/NetworkManager/dnsmasq-shared.d
cp "$SCRIPT_DIR/system/captive-portal.conf" /etc/NetworkManager/dnsmasq-shared.d/

# Disable Wi-Fi power-save. On the Pi 3 the brcmfmac driver parks the radio when
# idle, causing latency spikes and intermittent mDNS failures between tracks on
# this always-on player. 2 = disable in NetworkManager's enum.
mkdir -p /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/wifi-powersave-off.conf << 'PSCONF'
[connection]
wifi.powersave = 2
PSCONF

systemctl daemon-reload
systemctl enable megavox-setup.service
echo "  Done."

# --- Step 8: Configure permissions ---
echo "[8/8] Configuring permissions..."
# wifi_setup.py needs passwordless sudo for nmcli
cat > /etc/sudoers.d/megavox2000 << SUDOERS
$REAL_USER ALL=(ALL) NOPASSWD: /usr/bin/nmcli
SUDOERS
chmod 440 /etc/sudoers.d/megavox2000
echo "  Done."

# --- Complete ---
echo ""
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║           Installation complete!                 ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo ""
echo "  Next steps:"
if [ ! -f "$INSTALL_DIR/app/oauth_config.json" ]; then
    echo "    1. Add OAuth credentials to: $INSTALL_DIR/app/oauth_config.json"
    echo "    2. Reboot: sudo reboot"
else
    echo "    1. Reboot: sudo reboot"
fi
echo ""
echo "  After reboot:"
echo "    - If no Wi-Fi saved: connect to 'MegaVox2000-Setup' (password: mega2000)"
echo "    - If Wi-Fi connected: go to http://mega.local"
echo ""
