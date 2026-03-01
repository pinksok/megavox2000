# Building a MegaVox 2000 SD Card Image

Instructions for creating a pre-built SD card image that end users can flash and boot.

## What You Need

- Raspberry Pi 3B/3B+ (the target hardware)
- 16GB+ microSD card
- Ethernet cable or USB-serial adapter (for initial setup)
- A computer with an SD card reader (for imaging)
- Your Google OAuth credentials (client_id and client_secret)

## Step 1: Flash Base OS

Use Raspberry Pi Imager to write **Raspberry Pi OS Lite (64-bit, Bookworm)** to the SD card.

In the imager settings:
- Set username: `pi`, password: (your choice -- end users won't need it)
- Enable SSH (password authentication)
- Do NOT configure Wi-Fi (the device will create its own hotspot)

## Step 2: Boot and Connect

Insert the SD card in the Pi 3, connect Ethernet, and boot. SSH in:

```bash
ssh pi@raspberrypi.local
```

## Step 3: Install MegaVox 2000

```bash
sudo apt install -y git
git clone https://github.com/pinksok/megavox2000.git /tmp/megavox2000
cd /tmp/megavox2000
sudo bash install.sh
```

## Step 4: Add OAuth Credentials

```bash
cat > ~/megavox2000/app/oauth_config.json << 'EOF'
{
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET"
}
EOF
chmod 600 ~/megavox2000/app/oauth_config.json
```

## Step 5: Test

```bash
sudo reboot
```

After reboot:
1. Verify the "MegaVox2000-Setup" hotspot appears
2. Connect to it from a phone (password: mega2000)
3. Complete Wi-Fi setup
4. Go to http://mega.local
5. Sign in with Google
6. Play a song

## Step 6: Clean Up for Imaging

```bash
# Remove runtime data (each device generates its own)
rm -f ~/megavox2000/app/oauth.json
rm -f ~/megavox2000/app/history.json
rm -f ~/megavox2000/app/service.json
rm -f ~/megavox2000/app/volume.json

# Remove saved Wi-Fi connections (so hotspot starts on new network)
sudo nmcli connection delete "$(nmcli -t -f NAME,TYPE connection show | grep wireless | grep -v MegaVox | cut -d: -f1)" 2>/dev/null

# Clear logs and history
history -c && history -w
sudo journalctl --rotate && sudo journalctl --vacuum-time=1s

# Remove SSH host keys (regenerated on first boot)
sudo rm -f /etc/ssh/ssh_host_*

# Remove install source
sudo rm -rf /tmp/megavox2000

# Optional: zero free space for smaller compressed image
sudo dd if=/dev/zero of=/tmp/zero bs=1M 2>/dev/null; sudo rm /tmp/zero

sudo shutdown -h now
```

## Step 7: Image the SD Card

Remove the SD card and plug it into your computer.

```bash
# Find the SD card device
# macOS: diskutil list
# Linux: lsblk

# Create the image (replace /dev/sdX with your device)
sudo dd if=/dev/sdX of=megavox2000-v1.0.img bs=4M status=progress

# Shrink the image (optional but recommended)
# Download PiShrink: https://github.com/Drewsif/PiShrink
sudo ./pishrink.sh megavox2000-v1.0.img

# Compress for distribution
xz -9 megavox2000-v1.0.img
```

## Step 8: Distribute

Upload `megavox2000-v1.0.img.xz` to GitHub Releases:

```bash
gh release create v1.0 megavox2000-v1.0.img.xz \
    --title "MegaVox 2000 v1.0" \
    --notes "Pre-built SD card image for Raspberry Pi 3. Flash with Balena Etcher and boot."
```

## For Each New Device

1. Flash `megavox2000-v1.0.img.xz` to a new SD card (Balena Etcher handles .xz)
2. Insert in Pi 3, power on
3. Hand to recipient -- they connect to "MegaVox2000-Setup" Wi-Fi and follow the setup
