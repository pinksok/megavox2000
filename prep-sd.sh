#!/bin/bash
# MegaVox 2000 - SD Card Prep Script
# Run from Git Bash on Windows after flashing Pi OS Lite with Raspberry Pi Imager.
#
# Usage: bash prep-sd.sh E
#   (where E is the drive letter of the SD card's boot partition)

set -e

echo ""
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║         MegaVox 2000 — SD Card Prep             ║"
echo "  ║   MEGA BASS DIGITAL XBS PROCESSING SYSTEM        ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo ""

# --- Validate arguments ---
if [ -z "$1" ]; then
    echo "  Usage: bash prep-sd.sh <drive-letter>"
    echo "  Example: bash prep-sd.sh E"
    exit 1
fi

DRIVE="${1%%:}"  # Strip colon if provided (E: -> E)
BOOT="/$DRIVE"

# Check if drive exists and looks like a Pi OS boot partition
if [ ! -d "$BOOT" ]; then
    echo "  Error: Drive $DRIVE: not found at $BOOT"
    exit 1
fi

if [ ! -f "$BOOT/cmdline.txt" ]; then
    echo "  Error: $BOOT/cmdline.txt not found."
    echo "  This doesn't look like a Raspberry Pi OS boot partition."
    echo "  Flash Pi OS Lite first with Raspberry Pi Imager, then run this script."
    exit 1
fi

echo "  Target: $DRIVE: ($(ls "$BOOT/cmdline.txt" 2>/dev/null && echo 'Pi OS boot partition detected'))"

# --- Find repo directory (where this script lives) ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -f "$SCRIPT_DIR/install.sh" ] || [ ! -d "$SCRIPT_DIR/app" ]; then
    echo "  Error: Can't find MegaVox repo files. Run this script from the repo directory."
    exit 1
fi

echo "  Source: $SCRIPT_DIR"
echo ""

# --- Get OAuth credentials ---
echo "  YouTube OAuth credentials (from Google Cloud Console)."
echo "  Press Enter to skip (you can add them later on the Pi)."
echo ""
read -p "  Client ID: " CLIENT_ID
read -p "  Client Secret: " CLIENT_SECRET
echo ""

# --- Copy MegaVox files to boot partition ---
echo "[1/4] Copying MegaVox files to $DRIVE:\\megavox2000\\..."
DEST="$BOOT/megavox2000"
rm -rf "$DEST"
mkdir -p "$DEST/app/templates"
mkdir -p "$DEST/system"

# App files
cp "$SCRIPT_DIR/app/"*.py "$DEST/app/"
cp "$SCRIPT_DIR/app/favicon.svg" "$DEST/app/"
cp "$SCRIPT_DIR/app/oauth_config.json.example" "$DEST/app/"
cp "$SCRIPT_DIR/app/templates/"*.html "$DEST/app/templates/"

# System files
cp "$SCRIPT_DIR/system/"* "$DEST/system/"

# Install script
cp "$SCRIPT_DIR/install.sh" "$DEST/"

# OAuth config (if provided)
if [ -n "$CLIENT_ID" ] && [ -n "$CLIENT_SECRET" ]; then
    cat > "$DEST/app/oauth_config.json" << OAUTH
{
    "client_id": "$CLIENT_ID",
    "client_secret": "$CLIENT_SECRET"
}
OAUTH
    echo "  OAuth credentials saved."
else
    echo "  No OAuth credentials — skipped. Add them later:"
    echo "    ~/megavox2000/app/oauth_config.json"
fi
echo "  Done."

# --- Write firstrun.sh (append to Imager's if it exists) ---
echo "[2/4] Setting up first-boot auto-installer..."

# The MegaVox install block that runs on first boot
MEGAVOX_INSTALL=$(cat << 'MEGAVOX_BLOCK'

# === MegaVox 2000 First Boot Install ===
echo "=== MegaVox 2000 First Boot Install ==="
echo "Started: $(date)"

LOG="/var/log/megavox-firstrun.log"
exec > >(tee -a "$LOG") 2>&1

# Detect boot partition path (Bookworm uses /boot/firmware, older uses /boot)
if [ -d "/boot/firmware/megavox2000" ]; then
    BOOT_DIR="/boot/firmware"
elif [ -d "/boot/megavox2000" ]; then
    BOOT_DIR="/boot"
else
    echo "ERROR: megavox2000 files not found on boot partition!"
    exit 1
fi

echo "Boot partition: $BOOT_DIR"

# Wait for network (needed for apt/pip installs)
echo "Waiting for network..."
for i in $(seq 1 90); do
    if ping -c 1 -W 2 deb.debian.org > /dev/null 2>&1; then
        echo "Network ready after ${i}s."
        break
    fi
    if [ "$i" -eq 90 ]; then
        echo "WARNING: No network after 90s. Install may fail."
    fi
    sleep 1
done

# Detect the first non-root user (typically 'pi', UID 1000)
REAL_USER=$(getent passwd 1000 | cut -d: -f1)
if [ -z "$REAL_USER" ]; then
    REAL_USER="pi"
fi
REAL_HOME=$(eval echo "~$REAL_USER")
echo "Install user: $REAL_USER ($REAL_HOME)"

# Copy files from boot partition to home directory
echo "Copying MegaVox files..."
mkdir -p "$REAL_HOME/megavox2000"
cp -r "$BOOT_DIR/megavox2000/"* "$REAL_HOME/megavox2000/"
chown -R "$REAL_USER:$REAL_USER" "$REAL_HOME/megavox2000"
chmod 755 "$REAL_HOME/megavox2000/install.sh"

# Protect OAuth credentials
if [ -f "$REAL_HOME/megavox2000/app/oauth_config.json" ]; then
    chmod 600 "$REAL_HOME/megavox2000/app/oauth_config.json"
fi

# Run the MegaVox installer
echo "Running MegaVox installer..."
cd "$REAL_HOME/megavox2000"
SUDO_USER="$REAL_USER" bash install.sh

# Clean up boot partition (free up space, remove sensitive files)
echo "Cleaning up boot partition..."
rm -rf "$BOOT_DIR/megavox2000"

# Remove the firstrun trigger from cmdline.txt
sed -i 's| systemd.run=/boot/firmware/firstrun.sh||' "$BOOT_DIR/cmdline.txt"
sed -i 's| systemd.run=/boot/firstrun.sh||' "$BOOT_DIR/cmdline.txt"
sed -i 's| systemd.run_success_action=reboot||' "$BOOT_DIR/cmdline.txt"
sed -i 's| systemd.after=network-online.target||' "$BOOT_DIR/cmdline.txt"

echo "=== MegaVox 2000 Install Complete ==="
echo "Finished: $(date)"
echo "Rebooting in 5 seconds..."
sleep 5
reboot
MEGAVOX_BLOCK
)

if [ -f "$BOOT/firstrun.sh" ]; then
    # Imager's firstrun.sh exists — append MegaVox install to it
    echo "  Found Imager's firstrun.sh — appending MegaVox installer."

    # Remove Imager's self-cleanup and exit so our code runs after it
    sed -i '/^rm -f .*firstrun\.sh/d' "$BOOT/firstrun.sh"
    sed -i '/^exit 0/d' "$BOOT/firstrun.sh"

    # Append MegaVox install block
    echo "$MEGAVOX_INSTALL" >> "$BOOT/firstrun.sh"
else
    # No Imager firstrun — write standalone (ethernet required)
    echo "  No Imager firstrun.sh found — writing standalone installer."
    echo "  NOTE: Ethernet will be required on first boot."
    cat > "$BOOT/firstrun.sh" << 'STANDALONE'
#!/bin/bash
set -e
STANDALONE
    echo "$MEGAVOX_INSTALL" >> "$BOOT/firstrun.sh"
fi

chmod +x "$BOOT/firstrun.sh"
echo "  Done."

# --- Modify cmdline.txt to trigger firstrun (only if not already set) ---
echo "[3/4] Setting up first-boot trigger..."
CMDLINE="$BOOT/cmdline.txt"

if grep -q "systemd.run=" "$CMDLINE"; then
    # Imager already set up the trigger — leave it alone
    echo "  First-boot trigger already configured by Imager."
else
    # No trigger — add one (standalone/ethernet case)
    if grep -q "boot/firmware" "$CMDLINE" || [ -f "$BOOT/config.txt" ]; then
        FIRSTRUN_PATH="/boot/firmware/firstrun.sh"
    else
        FIRSTRUN_PATH="/boot/firstrun.sh"
    fi

    EXISTING=$(tr -d '\r\n' < "$CMDLINE" | sed 's/ *$//')
    echo "${EXISTING} systemd.run=${FIRSTRUN_PATH} systemd.run_success_action=reboot systemd.after=network-online.target" > "$CMDLINE"
    echo "  Trigger: systemd.run=${FIRSTRUN_PATH}"
fi
echo "  Done."

# --- Summary ---
echo "[4/4] Verifying..."
echo ""

FILE_COUNT=$(find "$DEST" -type f | wc -l)
echo "  Files copied: $FILE_COUNT"

if [ -f "$DEST/app/oauth_config.json" ]; then
    echo "  OAuth:        configured"
else
    echo "  OAuth:        not configured (add later)"
fi

echo "  First-boot:   enabled"
echo ""
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║              SD Card Ready!                      ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo ""
echo "  Next steps:"
echo "    1. Safely eject the SD card"
echo "    2. Insert into Raspberry Pi 3"
echo "    3. Power on and wait ~5-10 minutes"
echo "    4. Pi will connect to Wi-Fi, install, and reboot"
echo "    5. Visit http://mega.local from any device on your network"
echo ""
echo "  On a new network (no saved Wi-Fi):"
echo "    - Connect to 'MegaVox2000-Setup' hotspot (password: mega2000)"
echo ""
echo "  Install log on the Pi: /var/log/megavox-firstrun.log"
echo ""
