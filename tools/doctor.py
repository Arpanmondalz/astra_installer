#!/usr/bin/env python3
"""On-Pi diagnostics.  Run with:  python3 tools/doctor.py

Reports what the sensor actually supports, grabs a test frame and measures its
brightness, so "the preview is black" can be attributed to exposure, focus or
the pipeline rather than guessed at.
"""

from __future__ import annotations

import os
import shutil
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def heading(text: str) -> None:
    print(f"\n--- {text} " + "-" * max(0, 60 - len(text)))


def check_port(port: int = 80) -> None:
    heading(f"TCP port {port}")
    with socket.socket() as sock:
        sock.settimeout(2)
        try:
            sock.connect(("127.0.0.1", port))
            print(f"  OK: something is listening on {port}")
        except OSError as exc:
            print(f"  NOT LISTENING: {exc}")


def primary_ip() -> str | None:
    """The address this Pi uses to reach the network. Opens no connection."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("192.0.2.1", 1))  # TEST-NET-1, never routed
            return sock.getsockname()[0]
        except OSError:
            return None


def check_network(port: int = 80) -> None:
    heading("How to reach Astra")
    hostname = socket.gethostname()
    suffix = "" if port == 80 else f":{port}"
    print(f"  hostname          {hostname}")

    mdns = "running" if os.path.exists("/run/avahi-daemon/pid") else "NOT running"
    print(f"  avahi (mDNS)      {mdns}")

    address = primary_ip()
    print(f"  IP address        {address or 'not connected'}")
    print()
    print(f"  Open  http://{hostname}.local{suffix}")
    if address:
        print(f"  or    http://{address}{suffix}")
    if mdns != "running":
        print("\n  mDNS is off, so the .local name will not resolve.")
        print("  sudo systemctl enable --now avahi-daemon")


def check_resources() -> None:
    heading("Disk and memory")
    usage = shutil.disk_usage("/")
    free_mb = usage.free // (1024 * 1024)
    print(f"  root filesystem   {free_mb} MB free of {usage.total // (1024 * 1024)} MB")
    if free_mb < 200:
        print("  LOW: free space with  sudo ./deploy/slim.sh")

    try:
        with open("/proc/meminfo") as handle:
            meminfo = dict(
                (line.split(":", 1)[0], line.split()[1]) for line in handle if ":" in line
            )
        print(f"  memory available  {int(meminfo['MemAvailable']) // 1024} MB")
    except (OSError, KeyError, IndexError):
        pass

    # Astra streams captures straight to the browser, so the card should not grow.
    print("  note: Astra writes no images to the SD card")


def main() -> int:
    port = int(os.environ.get("ASTRA_PORT", 80))
    check_resources()

    heading("Camera detection")
    try:
        from picamera2 import Picamera2
    except ImportError as exc:
        print(f"  picamera2 is not installed: {exc}")
        print("  sudo apt install -y --no-install-recommends python3-picamera2")
        check_network(port)
        return 1

    cameras = Picamera2.global_camera_info()
    if not cameras:
        print("  No cameras found.")
        print("  Check the ribbon cable orientation and that /boot/firmware/config.txt")
        print("  contains 'camera_auto_detect=1' (or 'dtoverlay=ov5647'), then reboot.")
        check_network(port)
        return 1
    for info in cameras:
        print(f"  {info}")

    picam2 = Picamera2()

    heading("Sensor modes")
    for mode in picam2.sensor_modes:
        print(
            f"  {mode['size'][0]}x{mode['size'][1]}"
            f"  bit_depth={mode.get('bit_depth')}"
            f"  fps<={mode.get('fps')}"
            f"  crop={mode.get('crop_limits')}"
        )

    heading("Control limits (min, max, default)")
    for name in ("ExposureTime", "AnalogueGain", "ExposureValue", "FrameDurationLimits"):
        print(f"  {name:<20} {picam2.camera_controls.get(name)}")

    from astra import config
    from astra.camera import limits_from_controls

    limits = limits_from_controls(picam2.camera_controls)
    print(f"\n  Astra will expose exposure {limits.exposure_us[0]}-{limits.exposure_us[1]} us")
    print(f"  Astra will expose gain     {limits.gain[0]}-{limits.gain[1]}x")

    heading("Test capture")
    cfg = picam2.create_still_configuration(
        main={"size": config.STREAM_SIZE, "format": "RGB888"}, buffer_count=1
    )
    picam2.configure(cfg)
    picam2.start()
    time.sleep(2)
    array = picam2.capture_array("main")
    metadata = picam2.capture_metadata()
    picam2.stop()
    picam2.close()

    mean = float(array.mean())
    print(f"  frame shape       {array.shape}")
    print(f"  mean pixel value  {mean:.1f} / 255")
    print(f"  ExposureTime      {metadata.get('ExposureTime')} us")
    print(f"  AnalogueGain      {metadata.get('AnalogueGain')}")
    print(f"  DigitalGain       {metadata.get('DigitalGain')}")
    print(f"  Lux               {metadata.get('Lux')}")

    if mean < 2:
        print("\n  Frame is essentially black. In order of likelihood:")
        print("    1. lens cap / mirror cover still on, or telescope badly out of focus")
        print("    2. exposure far too short for the target")
        print("    3. camera ribbon seated incorrectly")
    elif mean > 240:
        print("\n  Frame is blown out - reduce exposure, gain or EV.")
    else:
        print("\n  Exposure looks sane.")

    check_port(port)
    check_network(port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
