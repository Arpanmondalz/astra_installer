# Astra

Turn a Raspberry Pi Zero 2 W and a 114 mm Newtonian telescope into a camera you
can watch and control from your phone. No eyepiece, no cables — open a web page,
point the telescope, tap a preset, save the picture.

Lightweight by design: it runs on Raspberry Pi OS Lite and needs very little
disk or memory.

---

## 1. What you need

**Electronics**

| Part | Notes |
| --- | --- |
| Raspberry Pi Zero 2 W | |
| OV5647 camera module (5 MP) | The lens must be **unscrewed and removed** so the bare sensor sits at the telescope's focal point |
| Pi Zero camera cable | 22-pin to 15-pin. A normal Raspberry Pi camera cable will **not** fit |
| microSD card | 4 GB minimum, 8 GB or larger recommended, Class 10 |
| 5 V power | A phone charger, or an 18650 cell with a 5 V boost module |

**On your computer**

- [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
- A microSD card reader

A small heatsink on the Pi is worth adding. Video encoding makes a bare Zero 2 W
run hot and slow itself down.

---

## 2. Flash the SD card

Open Raspberry Pi Imager and set:

- **Device:** Raspberry Pi Zero 2 W
- **Operating System:** Raspberry Pi OS (other) → **Raspberry Pi OS Lite (32-bit)**
- **Storage:** your microSD card

> Choose **32-bit**, not 64-bit. On a Pi Zero 2 W it uses noticeably less disk
> and less memory, and the camera stack is identical.

Before clicking **Write**, click the gear icon / **Edit Settings** and fill in:

- **Hostname:** `astra`
- **Enable SSH** — with password authentication
- **Username and password** — write these down
- **Wi-Fi SSID and password** — your normal home Wi-Fi, just for the setup
- **Locale, keyboard, timezone**

Click **Write** and wait. When it finishes, eject the card, put it in the Pi,
connect the camera ribbon, and power it on. Wait about two minutes for the first
boot.

---

## 3. Connect to the Pi

From your computer, open a terminal (PowerShell on Windows) and run:

```bash
ssh <your-username>@astra.local
```

Type `yes` when it asks about the fingerprint, then your password.

> **If `astra.local` doesn't work**, find the Pi's IP address in your router's
> device list and use that instead, e.g. `ssh pi@192.168.1.47`.

---

## 4. Update the system

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt clean
sudo reboot
```

`sudo apt clean` at the end matters on a small card — it throws away the
downloaded package files, which can easily be a few hundred megabytes.

Wait a minute, then SSH back in.

---

## 5. Copy Astra onto the Pi

Pick **one** of these.

**Option A — copy from your computer**

Use this if you have edited the files locally. Open a *new* terminal on your
computer, in the folder that contains `astra/`, `deploy/` and `tools/`:

```bash
scp -r astra deploy tools README.md pyproject.toml <your-username>@astra.local:~/astra-src
```

Then in your SSH session:

```bash
mv ~/astra-src ~/astra
```

> Copy only those folders. Do **not** copy `.venv` — it is for testing on your
> computer and is useless (and large) on the Pi.

**Option B — download it straight onto the Pi (easiest)**

Run these in your SSH session. No git required:

```bash
mkdir -p ~/astra && cd ~/astra
curl -L https://github.com/Arpanmondalz/astra_installer/archive/refs/heads/main.tar.gz | tar xz --strip-components=1
ls
```

`ls` should list `astra`, `deploy`, `tools` and `README.md`.

> If that fails, the repository's default branch may be called `master`. Run the
> same command with `master` in place of `main`.

If you would rather use git and have room for it:

```bash
sudo apt install -y git
git clone https://github.com/Arpanmondalz/astra_installer.git ~/astra
```

**Option C — use the SD card.** Before the first boot, copy the folder into the
small `bootfs` partition that Windows can see. Then on the Pi:

```bash
cp -r /boot/firmware/astra ~/astra
```

---

## 6. Run the installer

```bash
cd ~/astra
chmod +x deploy/*.sh
sudo ./deploy/install.sh
sudo reboot
```

This takes a few minutes. It installs about **90 MB** of packages, enables the
camera, turns off Wi-Fi power saving, shrinks the swap file, moves logs into RAM
and sets Astra to start automatically at every boot.

It prints your free disk space before and after.

---

## 7. Check that it works

SSH back in and run:

```bash
cd ~/astra
python3 tools/doctor.py
```

This tells you the camera model, the exposure range your sensor supports, and
whether a test picture came out black. Then:

```bash
systemctl status astra
```

You want to see `active (running)` in green.

---

## 8. Open it in your browser

Astra starts automatically every time the Pi powers on. There is nothing to log
into and nothing to launch.

Power the Pi on, wait about a minute, then on any phone, tablet or computer
**connected to the same Wi-Fi**, open:

```
http://astra.local
```

You should see the live view and the controls. If you have not focused the
telescope yet, expect a white blur or blackness — that is normal.

That is the whole everyday routine: switch on, wait, open the page.

### If `astra.local` does not load

The `.local` name relies on mDNS. Apple devices and Windows 10/11 handle it
well; some Android phones and some routers do not. Use the Pi's IP address
instead.

Find it by running this on the Pi:

```bash
python3 ~/astra/tools/doctor.py
```

It prints a "How to reach Astra" section with the exact addresses to type. Or
more directly:

```bash
hostname -I
```

Then open `http://192.168.1.47` (or whatever it shows) in your browser.

**Make that address permanent.** By default your router can hand the Pi a
different IP after a reboot. In your router's admin page, find the DHCP or
"connected devices" section, locate `astra`, and choose **Reserve IP** /
**Static lease** / **DHCP reservation**. From then on the address never changes
and you can bookmark it or turn it into a QR code.

> If you chose a hostname other than `astra` when flashing the card, use that
> name instead — e.g. `http://mypi.local`.

---

## Using Astra

### Presets

| Preset | Use it for |
| --- | --- |
| **Moon** | The Moon. Start here — it's by far the easiest target |
| **Planets** | Jupiter, Saturn, Mars |
| **Deep Sky** | Star clusters and nebulae |
| **Daylight** | Daytime practice and focusing on a distant object |
| **Reset** | Put everything back to normal |

Tap a preset and the camera sorts itself out. You should not have to touch a
slider to see the Moon.

### Controls

- **Auto exposure** — leave this on for the Moon and planets. Turn it off only
  for long deep-sky exposures.
- **Brightness** — the one slider to reach for. Nudge it if the image is too
  dark or washed out.
- **Exposure / Gain** — only active when auto exposure is off. More gain means a
  brighter but grainier picture.
- **Sensor zoom** — a real zoom on the camera chip, not a fake stretch. Use 3–4×
  to help you focus, then zoom back out.
- **Mono** — black and white. Removing the camera lens also removed its infrared
  filter, which is what causes the pink tint. Mono avoids it and actually shows
  more detail on the Moon.
- **Capture** — saves the picture you're looking at, straight to your phone.
- **Capture full 5 MP** — a higher resolution shot. The preview pauses for a
  couple of seconds.
- **Advanced → Continuous stream** — smoother video when you are standing next
  to the telescope, but less reliable at a distance. Off by default.

### Focusing

This is the part that trips everyone up.

1. Do your first attempt **in daylight**, on something far away like a rooftop.
   Use the **Daylight** preset.
2. Turn the focus knob **slowly**. A telescope goes from a shapeless blur to
   sharp over a very small amount of travel — it is easy to spin straight past it.
3. Set **Sensor zoom** to 3–4× while focusing. It's much easier to judge.
4. At night, start with the Moon and the **Moon** preset.

If you can't get it sharp at all, the mirror may need collimating — small
adjustments on the three bolts behind the primary mirror.

---

## Disk space

Roughly what to expect:

| | Space |
| --- | --- |
| Raspberry Pi OS Lite 32-bit, fresh | ~1.4 GB used |
| Astra and its dependencies | ~90 MB |

Astra itself never grows: pictures stream directly to your phone and are never
written to the SD card, and logs are kept in RAM. A 4 GB card is enough; 8 GB or
more leaves comfortable headroom.

If you are running short, the optional cleanup removes documentation, manual
pages and non-English translations:

```bash
sudo ./deploy/slim.sh
```

That usually frees another 150–250 MB.

Other easy wins:

```bash
sudo apt clean                          # after any apt install
df -h /                                 # check free space
sudo du -xh --max-depth=1 / | sort -h   # find what is using it
```

---

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Page won't load | `systemctl status astra`, then `journalctl -u astra -n 50` |
| "No cameras found" | Check the ribbon cable is the right way round and fully seated. Confirm `camera_auto_detect=1` is in `/boot/firmware/config.txt`, then reboot |
| Preview is black | Run `python3 tools/doctor.py`. If it reports a mean pixel value under 2: the cover is on, the telescope is badly out of focus, or the exposure is too short |
| Picture is pink | Turn on **Mono**, or adjust the red/blue gains under Advanced |
| Preview freezes after sitting idle | Wi-Fi power saving. `iw dev wlan0 get power_save` should say `off` |
| `astra.local` doesn't resolve | Use the IP address instead — see [If `astra.local` does not load](#if-astralocal-does-not-load). Android phones in particular don't handle `.local` names |
| Address changed after a reboot | Reserve a fixed IP for `astra` in your router's DHCP settings |
| Deep Sky exposure seems short | The OV5647's maximum exposure is modest. `doctor.py` prints the real limit; raise gain instead |
| Out of disk space | `sudo apt clean`, then `sudo ./deploy/slim.sh` |

Useful commands:

```bash
sudo systemctl restart astra     # restart it
journalctl -u astra -f           # watch the log live
curl -s localhost/healthz        # is the camera alive
df -h /                          # free space
```

---

### Optional — standalone Wi-Fi hotspot

Everything above works on your home Wi-Fi. Do this step only when you want to
take the telescope somewhere with no network, and only **after** you have
confirmed Astra works.

The Pi will create its own Wi-Fi network called `Astra` that your phone joins
directly.

```bash
cd ~/astra
sudo ./deploy/hotspot.sh 'choose-a-password'
```

Pick a password of at least 8 characters. Then activate it:

```bash
sudo nmcli connection up Astra
```

> This immediately disconnects the Pi from your home Wi-Fi, which means **your
> SSH session will drop**. That is expected.

Now on your phone: join the Wi-Fi network named **Astra**, then open

```
http://192.168.4.1
```

Print that as a QR code and stick it on the telescope tube.

**Going back to home Wi-Fi:**

```bash
sudo nmcli connection up <your-home-ssid>
```

**To stop it auto-joining your home network in the field:**

```bash
sudo nmcli connection modify <your-home-ssid> connection.autoconnect no
```

---

### Optional — for developers

The camera layer is isolated, so everything else runs and is tested on an
ordinary PC with no Pi hardware:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

| Path | Purpose |
| --- | --- |
| `astra/settings.py` | Settings model, validation and clamping. No hardware imports |
| `astra/presets.py` | Observing presets |
| `astra/geometry.py` | Sensor crop maths for zoom |
| `astra/framebuffer.py` | Latest-frame handoff between encoder and HTTP threads |
| `astra/camera.py` | Picamera2 pipeline, supervisor and stall recovery |
| `astra/web.py` | Flask routes |
| `astra/templates`, `astra/static` | Front end |
| `deploy/` | systemd unit, installer, slimming and hotspot scripts |
| `tools/doctor.py` | On-Pi diagnostics |

Configuration is environment driven - see `astra/config.py` for every knob
(`ASTRA_PORT`, `ASTRA_STREAM_SIZE`, `ASTRA_STREAM_FPS`, ...). To run against a
different port while developing on the Pi:

```bash
sudo systemctl stop astra
ASTRA_PORT=8080 python3 -m astra
```

---

### Optional: Safe Battery Disconnect (OverlayFS)


Because Astra is designed for headless use out in the field, turning it off means simply disconnecting the battery. Doing this on a normal Raspberry Pi will eventually corrupt the file system and ruin the microSD card.

Since Astra sends pictures straight to your phone and keeps its logs in RAM, it doesn't actually need to write anything to the disk. You can make the entire filesystem **read-only**. This locks the SD card, making it 100% safe to pull the power plug at any time.

**To lock the filesystem:**
1. SSH into the Pi and open the configuration tool:
   ```bash
   sudo raspi-config
   ```

2. Navigate to **4 Performance Options** > **P2 Overlay File System**.
3. Select **Yes** when asked to enable the overlay file system.
4. Select **Yes** when asked to write-protect the boot partition.
5. Exit the tool and select **Yes** to reboot.

> **Important for future updates:** Once OverlayFS is enabled, the Pi acts like a locked physical cartridge. *Any* changes you make (like updating code, saving a new Wi-Fi password, or changing hotspot settings) will completely vanish the next time the power is cut. When you need to update Astra, run `sudo raspi-config`, disable the overlay, reboot, make your changes, and then re-enable it.

### Optional: Add a secondary wifi network for backup
This is an optional step to add a second wifi network (like a smartphone hotspot) when the primary wifi network is out of range. 

> **Note on OverlayFS:** If you currently have OverlayFS (read-only mode) enabled, you must disable it via `sudo raspi-config` and reboot before running these commands, or the new Wi-Fi profile will disappear on the next reboot.

1. **Create the network profile:**
```bash
sudo nmcli connection add type wifi con-name "SECOND_SSID" ifname wlan0 ssid "SECOND_SSID"

```

2. **Save the password:**
```bash
sudo nmcli connection modify "SECOND_SSID" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "SECOND_PASSWORD"

```

3. **Ensure auto-connect is active:**
```bash
sudo nmcli connection modify "SECOND_SSID" connection.autoconnect yes

```

*Verification:* Run `nmcli connection show` to confirm the new `SECOND_SSID` entry appears in the list.

---

### Set Network Priority (Recommended)

To ensure the Pi always prefers your primary home network whenever both are in range, set a higher priority for your primary Wi-Fi and a lower priority for the backup network:

```bash
sudo nmcli connection modify "PRIMARY_SSID" connection.autoconnect-priority 10
sudo nmcli connection modify "SECOND_SSID" connection.autoconnect-priority 5

```


## Credits

Optical design derived from the [PiKon telescope](https://pikonic.com/) project.
Rewritten software, presets and mounts for the Astra build.
