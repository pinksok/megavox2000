#!/bin/bash
# MegaVox 2000 - Boot-time Wi-Fi check and port redirect
# Runs as root via megavox-setup.service

MODE_FILE="/tmp/megavox-mode"
HOTSPOT_CON="MegaVox2000-Setup"
HOTSPOT_SSID="MegaVox2000-Setup"
APP_USER="pi"

case "$1" in
    start)
        # Wait for NetworkManager to be fully ready
        sleep 3

        # Always add port 80 -> 5000 redirect so http://mega.local works
        iptables -t nat -C PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 5000 2>/dev/null || \
            iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 5000
        iptables -t nat -C OUTPUT -p tcp -o lo --dport 80 -j REDIRECT --to-port 5000 2>/dev/null || \
            iptables -t nat -A OUTPUT -p tcp -o lo --dport 80 -j REDIRECT --to-port 5000

        # Check if wlan0 has an active non-AP wifi connection
        ACTIVE_WIFI=$(nmcli -t -f TYPE,STATE connection show --active 2>/dev/null | grep "802-11-wireless:activated")

        if [ -z "$ACTIVE_WIFI" ]; then
            # No active wifi - wait for auto-connect
            echo "No Wi-Fi connection detected. Waiting 10s for auto-connect..."
            sleep 10
            ACTIVE_WIFI=$(nmcli -t -f TYPE,STATE connection show --active 2>/dev/null | grep "802-11-wireless:activated")
        fi

        if [ -z "$ACTIVE_WIFI" ]; then
            # Still no wifi - start AP mode for setup
            echo "No Wi-Fi connection. Starting setup hotspot..."
            # Clean up any previous hotspot connection
            nmcli connection down "$HOTSPOT_CON" 2>/dev/null
            nmcli connection delete "$HOTSPOT_CON" 2>/dev/null
            # Start hotspot with explicit password and WPS disabled
            nmcli device wifi hotspot ifname wlan0 con-name "$HOTSPOT_CON" ssid "$HOTSPOT_SSID" band bg password "mega2000" 2>&1
            nmcli connection modify "$HOTSPOT_CON" 802-11-wireless-security.wps-method 0 2>/dev/null
            echo "ap" > "$MODE_FILE"
            echo "Setup hotspot started: $HOTSPOT_SSID"
        else
            echo "Wi-Fi connected."
            echo "client" > "$MODE_FILE"
        fi

        chown "$APP_USER:$APP_USER" "$MODE_FILE"
        chmod 644 "$MODE_FILE"
        ;;

    stop)
        # Remove iptables redirect
        iptables -t nat -D PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 5000 2>/dev/null
        iptables -t nat -D OUTPUT -p tcp -o lo --dport 80 -j REDIRECT --to-port 5000 2>/dev/null
        # Stop hotspot if running
        nmcli connection down "$HOTSPOT_CON" 2>/dev/null
        nmcli connection delete "$HOTSPOT_CON" 2>/dev/null
        rm -f "$MODE_FILE"
        ;;
esac
