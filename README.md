# Astra raspberry pi setup guide


### 1) Hardware

* Raspberry Pi Zero 2 W


* microSD card, 4 GB minimum (8 GB or larger recommended)


* Raspberry Pi Camera


* Power supply (or field battery)



### 2) Flash Raspberry Pi OS Lite

Open Raspberry Pi Imager and configure it as follows:

* **Device:** Raspberry Pi Zero 2 W


* **Operating System:** Raspberry Pi OS Lite (32-bit)


* **Storage:** Select your microSD card



Before clicking **Write**, open the advanced options (or Edit Settings) and configure:

* **Hostname:** `astra`

* Enable SSH


* Set a username and password


* Configure your primary Home Wi-Fi SSID and password


* Set your locale, keyboard layout, and timezone



Click **Write**, wait for verification, then insert the card into the Pi and power it on. Give it about 1-2 minutes for the first boot.

### 3) First Boot & Update

SSH into the Pi from your computer:
`ssh <username>@astra.local`

Run the following to update your system:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo reboot
```

*(Log back in via SSH after it reboots).*

### 4) Install Dependencies

Install the required packages for the web server and local network discovery:
```bash
sudo apt install python3-flask python3-waitress avahi-daemon
```

### 5) Create the Astra App

Create the project folder and the main script:

```bash
mkdir -p ~/astra
cd ~/astra
nano ~/astra/app.py
```

Paste the `app.py` from this repo into this file, then save and exit

### 6) Run Astra on Startup

Create a systemd service so Astra runs automatically when the Pi turns on:
```bash
sudo nano /etc/systemd/system/astra.service
```

Paste this service file, replacing `YOUR_USER` with your Linux username:

```ini
[Unit]
Description=Astra Telescope Server
After=network-online.target avahi-daemon.service
Wants=network-online.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/astra
ExecStart=/usr/bin/python3 /home/YOUR_USER/astra/app.py
Restart=always
RestartSec=2
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable astra.service
sudo systemctl start astra.service
```

---

### 7) Optional: Add a Secondary Wi-Fi Network (For Field Backup)

This is an optional step to add a second Wi-Fi network (like your smartphone's mobile hotspot) for when your primary home Wi-Fi is out of range.

**Note on OverlayFS:** If you already enabled OverlayFS (read-only mode) in Step 8, you **must** disable it via `sudo raspi-config` and reboot before running these commands, or the new Wi-Fi profile will disappear on the next reboot.

Create the network profile:
```bash
sudo nmcli connection add type wifi con-name "SECOND_SSID" ifname wlan0 ssid "SECOND_SSID"
```

Save the password:
```bash
sudo nmcli connection modify "SECOND_SSID" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "SECOND_PASSWORD"
```

Ensure auto-connect is active:
```bash
sudo nmcli connection modify "SECOND_SSID" connection.autoconnect yes
```

**Set Network Priority (Recommended)**

To ensure the Pi always prefers your primary home network whenever both are in range, set a higher priority for your primary Wi-Fi and a lower priority for the backup network:

```bash
sudo nmcli connection modify "PRIMARY_SSID" connection.autoconnect-priority 10
sudo nmcli connection modify "SECOND_SSID" connection.autoconnect-priority 5

```

Run `nmcli connection show` to confirm both networks appear in the list.

---

### 8) Highly Recommended: Safe Battery Disconnect (OverlayFS)

Because Astra is designed for headless use out in the field, turning it off means simply disconnecting the battery. Doing this on a normal Raspberry Pi will eventually corrupt the file system and ruin the microSD card.

Since Astra sends pictures straight to your phone and keeps its logs in RAM, it doesn't actually need to write anything to the disk. You can make the entire filesystem read-only. This locks the SD card, making it **100% safe to pull the power plug at any time**.

**To lock the filesystem:**

1. SSH into the Pi and open the configuration tool:
```bash
sudo raspi-config
```
2. Navigate to **4 Performance Options** > **P2 Overlay File System**.
3. Select **Yes** when asked to enable the overlay file system.
4. Select **Yes** when asked to write-protect the boot partition.
5. Exit the tool and select **Yes** to reboot.

**Important for future updates:** Once OverlayFS is enabled, the Pi acts like a locked physical cartridge. Any changes you make (like updating code, saving a new Wi-Fi password, or changing network priorities) will completely vanish the next time the power is cut. When you need to update Astra, run `sudo raspi-config`, disable the overlay, reboot, make your changes, and then re-enable it.

---

### 9) Use Astra

Out in the field, turn on your smartphone hotspot (if using backup Wi-Fi) and power up the Pi. Connect your viewing device to the active Wi-Fi network and navigate to:
**[http://astra.local](http://astra.local?utm_source=gemini)**