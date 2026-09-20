#!/usr/bin/env bash
# Turn the Pi into a standalone "Astra" access point.
# Usage:  sudo ./deploy/hotspot.sh 'your-wifi-password'
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "Run with sudo: sudo ./deploy/hotspot.sh 'password'" >&2
    exit 1
fi

PASSWORD="${1:-}"
if [[ ${#PASSWORD} -lt 8 ]]; then
    echo "Give a WPA2 password of at least 8 characters." >&2
    exit 1
fi

CON=Astra
IFACE="${ASTRA_IFACE:-wlan0}"
ADDRESS=192.168.4.1/24

nmcli connection delete "${CON}" 2>/dev/null || true

nmcli connection add type wifi ifname "${IFACE}" con-name "${CON}" \
    autoconnect yes ssid "${CON}"

nmcli connection modify "${CON}" \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    802-11-wireless.channel 6 \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.proto rsn \
    wifi-sec.pairwise ccmp \
    wifi-sec.psk "${PASSWORD}" \
    wifi.powersave 2 \
    connection.autoconnect-priority 100

# "shared" mode runs the DHCP server. Pinning ipv4.addresses as well as the
# method is what stops NetworkManager falling back to 10.42.0.1, so the QR code
# on the tube always points at a working address.
nmcli connection modify "${CON}" \
    ipv4.method shared \
    ipv4.addresses "${ADDRESS}" \
    ipv6.method ignore

echo
echo "Hotspot profile created."
echo "Activate it (this will drop your current Wi-Fi/SSH session):"
echo "    sudo nmcli connection up ${CON}"
echo
echo "To stop joining your home network automatically:"
echo "    sudo nmcli connection modify <your-home-ssid> connection.autoconnect no"
echo
echo "Astra will then be at  http://192.168.4.1"
