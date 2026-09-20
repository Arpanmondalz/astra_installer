#!/usr/bin/env bash
# Reclaim disk space on a small SD card.  sudo ./deploy/slim.sh
#
# Removes documentation, man pages and non-English translations, and tells dpkg
# not to install them again. Typically frees 150-250 MB.
#
# This is opt-in and safe for a headless appliance, but it does delete files:
# `man` output disappears and non-English locales stop working. Undo by deleting
# /etc/dpkg/dpkg.cfg.d/01-astra-slim and reinstalling the affected packages.
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "Run with sudo:  sudo ./deploy/slim.sh" >&2
    exit 1
fi

if [[ ${1:-} != "--yes" ]]; then
    read -r -p "Delete docs, man pages and non-English locales? [y/N] " reply
    [[ ${reply} =~ ^[Yy]$ ]] || { echo "Cancelled."; exit 0; }
fi

free_mb() { df -Pm / | awk 'NR==2 {print $4}'; }
BEFORE_MB="$(free_mb)"

echo "==> Telling dpkg to skip docs and translations from now on"
cat > /etc/dpkg/dpkg.cfg.d/01-astra-slim <<'EOF'
path-exclude /usr/share/doc/*
path-include /usr/share/doc/*/copyright
path-exclude /usr/share/man/*
path-exclude /usr/share/groff/*
path-exclude /usr/share/info/*
path-exclude /usr/share/lintian/*
path-exclude /usr/share/locale/*
path-include /usr/share/locale/en*
path-include /usr/share/locale/locale.alias
EOF

echo "==> Removing what is already on disk"
find /usr/share/doc -mindepth 1 -not -name copyright -delete 2>/dev/null || true
rm -rf /usr/share/man/* /usr/share/groff/* /usr/share/info/* /usr/share/lintian/*
find /usr/share/locale -mindepth 1 -maxdepth 1 -type d ! -name 'en*' -exec rm -rf {} + 2>/dev/null || true

echo "==> Clearing caches"
apt-get autoremove --purge -y >/dev/null 2>&1 || true
apt-get clean
rm -rf /var/lib/apt/lists/* /var/cache/man /tmp/* 2>/dev/null || true

AFTER_MB="$(free_mb)"
echo
echo "Free space: ${BEFORE_MB} MB -> ${AFTER_MB} MB  (reclaimed $(( AFTER_MB - BEFORE_MB )) MB)"
