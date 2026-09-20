#!/usr/bin/env bash
# Install Astra on Raspberry Pi OS Lite (Bookworm).
# Run from the folder you copied to the Pi:  sudo ./deploy/install.sh
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "Run with sudo:  sudo ./deploy/install.sh" >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="${SUDO_USER:-pi}"
CONFIG_TXT=/boot/firmware/config.txt
[[ -f ${CONFIG_TXT} ]] || CONFIG_TXT=/boot/config.txt

free_mb() { df -Pm / | awk 'NR==2 {print $4}'; }
BEFORE_MB="$(free_mb)"
echo "==> Free space before: ${BEFORE_MB} MB"

echo "==> Installing packages"
apt-get update
# --no-install-recommends is not optional here: the recommended set pulls PyQt5
# and the OpenGL stack, roughly 400 MB that a headless server never touches.
# Everything else picamera2 needs (libcamera, kms++, numpy, PIL, simplejpeg)
# arrives automatically as a hard dependency.
apt-get install -y --no-install-recommends \
    python3-picamera2 \
    python3-flask \
    python3-waitress \
    avahi-daemon

echo "==> Enabling mDNS so http://<hostname>.local works"
# Already present on Raspberry Pi OS, but make sure it is actually running.
systemctl enable --now avahi-daemon >/dev/null 2>&1 || true

echo "==> Reclaiming the package cache"
apt-get clean
rm -rf /var/lib/apt/lists/*

if ! command -v rpicam-hello >/dev/null 2>&1; then
    echo "    note: rpicam-apps is not installed. Astra does not need it, but"
    echo "          'rpicam-hello' is handy for testing. Add it if you have room:"
    echo "          sudo apt install --no-install-recommends rpicam-apps-lite"
fi

echo "==> Enabling the camera"
if ! grep -q '^camera_auto_detect=1' "${CONFIG_TXT}"; then
    printf '\ncamera_auto_detect=1\n' >> "${CONFIG_TXT}"
fi
# The OV5647 is not always auto-detected on a Zero 2 W; pin the overlay.
if ! grep -q '^dtoverlay=ov5647' "${CONFIG_TXT}"; then
    printf 'dtoverlay=ov5647\n' >> "${CONFIG_TXT}"
fi

echo "==> Disabling Wi-Fi power save"
# Power save is the usual cause of a preview that freezes after idling.
install -d /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/10-astra-no-powersave.conf <<'EOF'
[connection]
wifi.powersave = 2
EOF

echo "==> Trimming services a telescope does not need"
for unit in bluetooth hciuart triggerhappy ModemManager; do
    systemctl disable --now "${unit}" >/dev/null 2>&1 || true
done

echo "==> Keeping logs in RAM"
# Saves SD space and write cycles, and survives the hard power-offs a battery
# powered telescope inevitably gets.
install -d /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/10-astra.conf <<'EOF'
[Journal]
Storage=volatile
RuntimeMaxUse=32M
EOF
rm -rf /var/log/journal

echo "==> Shrinking the swap file to 64 MB"
if [[ -f /etc/dphys-swapfile ]]; then
    sed -i 's/^#\?CONF_SWAPSIZE=.*/CONF_SWAPSIZE=64/' /etc/dphys-swapfile
    dphys-swapfile swapoff >/dev/null 2>&1 || true
    dphys-swapfile setup >/dev/null 2>&1 || true
    dphys-swapfile swapon >/dev/null 2>&1 || true
fi

echo "==> Installing the service"
sed -e "s|__USER__|${RUN_USER}|g" \
    -e "s|__WORKDIR__|${REPO_DIR}|g" \
    "${REPO_DIR}/deploy/astra.service" > /etc/systemd/system/astra.service

usermod -aG video "${RUN_USER}" || true

systemctl daemon-reload
systemctl enable astra.service
systemctl restart astra.service

AFTER_MB="$(free_mb)"
echo
echo "==> Free space after:  ${AFTER_MB} MB  (used $(( BEFORE_MB - AFTER_MB )) MB)"
echo
echo "Reboot to load the camera overlay:   sudo reboot"
echo "Then check:                          python3 tools/doctor.py"
echo "Astra will be at:                    http://$(hostname).local"
if (( AFTER_MB < 400 )); then
    echo
    echo "Space is tight. Free another ~150 MB with:   sudo ./deploy/slim.sh"
fi
