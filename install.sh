#!/bin/bash
set -e

# Magnavox 2000 - Installation Script
# Run on a fresh Raspberry Pi OS Lite (Bookworm or later)
# Usage: sudo bash install.sh

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║       Magnavox 2000 Installer    ║"
echo "  ╚══════════════════════════════════╝"
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
INSTALL_DIR="$REAL_HOME/magnavox2000"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "  User:      $REAL_USER (UID $REAL_UID)"
echo "  Install:   $INSTALL_DIR"
echo "  Source:    $SCRIPT_DIR"
echo ""

# --- Step 1: System packages ---
echo "[1/8] Installing system packages..."
apt-get update -qq
apt-get install -y -qq \
    python3-flask \
    python3-dbus \
    python3-gi \
    python3-requests \
    ffmpeg \
    pipewire \
    pipewire-pulse \
    wireplumber \
    bluetooth \
    bluez-tools \
    nodejs \
    network-manager \
    2>/dev/null

echo "  Done."

# --- Step 2: pip packages ---
echo "[2/8] Installing Python packages..."
pip3 install --break-system-packages yt-dlp qrcode ytmusicapi 2>/dev/null
echo "  Done."

# --- Step 3: Copy application files ---
echo "[3/8] Installing application files..."
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

# --- Step 5: Set hostname ---
echo "[5/8] Setting hostname to 'boombox'..."
hostnamectl set-hostname boombox
if grep -q "127.0.1.1" /etc/hosts; then
    sed -i 's/127\.0\.1\.1.*/127.0.1.1\tboombox/' /etc/hosts
else
    echo "127.0.1.1	boombox" >> /etc/hosts
fi
echo "  Done."

# --- Step 6: Install user service (magnavox2000.service) ---
echo "[6/8] Installing user service..."
USER_SERVICE_DIR="$REAL_HOME/.config/systemd/user"
mkdir -p "$USER_SERVICE_DIR"

# Generate service file with correct paths and UID
sed -e "s|INSTALL_DIR_PLACEHOLDER|$INSTALL_DIR|g" \
    -e "s|INSTALL_UID_PLACEHOLDER|$REAL_UID|g" \
    "$SCRIPT_DIR/system/magnavox2000.service" > "$USER_SERVICE_DIR/magnavox2000.service"

chown -R "$REAL_USER:$REAL_USER" "$REAL_HOME/.config"

# Enable lingering so user services start at boot without login
loginctl enable-linger "$REAL_USER"

# Reload and enable (needs user's runtime dir)
sudo -u "$REAL_USER" XDG_RUNTIME_DIR="/run/user/$REAL_UID" \
    systemctl --user daemon-reload
sudo -u "$REAL_USER" XDG_RUNTIME_DIR="/run/user/$REAL_UID" \
    systemctl --user enable magnavox2000.service
echo "  Done."

# --- Step 7: Install boot service (magnavox-setup.service) ---
echo "[7/8] Installing boot service..."

# Copy boot script and set the user
cp "$SCRIPT_DIR/system/magnavox-boot.sh" "$INSTALL_DIR/magnavox-boot.sh"
chmod +x "$INSTALL_DIR/magnavox-boot.sh"
sed -i "s|^APP_USER=.*|APP_USER=\"$REAL_USER\"|" "$INSTALL_DIR/magnavox-boot.sh"

# Generate system service with correct paths
sed -e "s|INSTALL_DIR_PLACEHOLDER|$INSTALL_DIR|g" \
    "$SCRIPT_DIR/system/magnavox-setup.service" > /etc/systemd/system/magnavox-setup.service

# Captive portal DNS config for AP mode
mkdir -p /etc/NetworkManager/dnsmasq-shared.d
cp "$SCRIPT_DIR/system/captive-portal.conf" /etc/NetworkManager/dnsmasq-shared.d/

systemctl daemon-reload
systemctl enable magnavox-setup.service
echo "  Done."

# --- Step 8: Configure permissions ---
echo "[8/8] Configuring permissions..."
# wifi_setup.py needs passwordless sudo for nmcli
cat > /etc/sudoers.d/magnavox2000 << SUDOERS
$REAL_USER ALL=(ALL) NOPASSWD: /usr/bin/nmcli
SUDOERS
chmod 440 /etc/sudoers.d/magnavox2000
echo "  Done."

# --- Complete ---
echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║     Installation complete!       ║"
echo "  ╚══════════════════════════════════╝"
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
echo "    - If no Wi-Fi saved: connect to 'Magnavox2000-Setup' (password: magnavox2000)"
echo "    - If Wi-Fi connected: go to http://boombox.local"
echo ""
