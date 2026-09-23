import atexit
import signal
import subprocess
import threading
import time
from datetime import datetime
from io import BytesIO

from flask import Flask, Response, redirect, render_template_string, request, send_file, url_for
from waitress import serve

app = Flask(__name__)

WIDTH = 1920
HEIGHT = 1080
FPS = 15

state_lock = threading.Lock()
frame_cond = threading.Condition()

# Updated default settings (Track Mode active by default)
DEFAULTS = {
    "hflip": False,
    "vflip": True,
    "track_mode": True,      # True = Auto Exposure/Gain, False = Manual
    "exposure_us": 50000,    # 50ms default (more reasonable than 1ms)
    "gain": 4.0,
    "brightness": 0.0,       # -1.0 to 1.0
    "sensor_zoom": 1.0,      # 1.0x to 4.0x Hardware ROI
}

camera_settings = DEFAULTS.copy()

latest_frame = None
latest_frame_id = 0

camera_proc = None
stop_event = threading.Event()
restart_event = threading.Event()

def clamp_int(value, low, high, default):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))

def clamp_float(value, low, high, default):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))

def build_camera_cmd():
    with state_lock:
        hflip = camera_settings["hflip"]
        vflip = camera_settings["vflip"]
        track_mode = camera_settings["track_mode"]
        exposure_us = camera_settings["exposure_us"]
        gain = camera_settings["gain"]
        brightness = camera_settings["brightness"]
        zoom = camera_settings["sensor_zoom"]

    cmd = [
        "rpicam-vid",
        "-n",
        "-t", "0",
        "--width", str(WIDTH),
        "--height", str(HEIGHT),
        "--framerate", str(FPS),
        "--codec", "mjpeg",
        "-o", "-",
    ]

    # If Manual Mode is active, enforce our manual exposure/gain/brightness
    if not track_mode:
        cmd.extend([
            "--shutter", str(exposure_us),
            "--gain", str(gain),
            "--brightness", str(brightness)
        ])

    # Hardware Sensor Zoom (ROI center cropping)
    if zoom > 1.0:
        w = 1.0 / zoom
        h = 1.0 / zoom
        x = (1.0 - w) / 2.0
        y = (1.0 - h) / 2.0
        cmd.extend(["--roi", f"{x:.4f},{y:.4f},{w:.4f},{h:.4f}"])

    if hflip:
        cmd.append("--hflip")
    if vflip:
        cmd.append("--vflip")

    return cmd

def camera_worker():
    global latest_frame, latest_frame_id, camera_proc

    while not stop_event.is_set():
        cmd = build_camera_cmd()
        
        # Start fresh buffer for each process instance
        buffer = bytearray()

        camera_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )

        try:
            while not stop_event.is_set() and not restart_event.is_set():
                chunk = camera_proc.stdout.read(4096)
                if not chunk:
                    break

                buffer.extend(chunk)

                while True:
                    start = buffer.find(b"\xff\xd8")
                    if start == -1:
                        # Memory Guard: Prevent buffer bloat on 512MB RAM
                        if len(buffer) > 3_000_000:
                            buffer.clear()
                        break

                    end = buffer.find(b"\xff\xd9", start + 2)
                    if end == -1:
                        if start > 0:
                            del buffer[:start]
                        break

                    frame = bytes(buffer[start:end + 2])
                    del buffer[:end + 2]

                    with frame_cond:
                        latest_frame = frame
                        latest_frame_id += 1
                        frame_cond.notify_all()

        finally:
            # Graceful shutdown to release hardware locks
            try:
                if camera_proc and camera_proc.poll() is None:
                    camera_proc.send_signal(signal.SIGINT)
                    try:
                        camera_proc.wait(timeout=1.5)
                    except subprocess.TimeoutExpired:
                        camera_proc.terminate()
                        camera_proc.wait(timeout=1)
            except Exception:
                pass

            restart_event.clear()
            # Settling delay for the camera ISP module
            time.sleep(0.5)

def mjpeg_generator():
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    last_seen_id = -1

    while not stop_event.is_set():
        with frame_cond:
            frame_cond.wait_for(
                lambda: latest_frame_id != last_seen_id or stop_event.is_set(),
                timeout=5,
            )

        if stop_event.is_set():
            break

        if latest_frame is None:
            continue

        frame = latest_frame
        last_seen_id = latest_frame_id

        yield boundary + frame + b"\r\n"

INDEX_HTML = """
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Astra</title>
    <style>
        * { box-sizing: border-box; }
        body { margin: 0; background: #141414; color: #e5e5e5; font-family: system-ui, sans-serif; }
        header { height: 56px; display: flex; align-items: center; padding: 0 20px; background: #1b1b1b; border-bottom: 1px solid #2f2f2f; font-size: 22px; font-weight: 600; letter-spacing: 1px; }
        .container { max-width: 1100px; margin: 24px auto; padding: 0 20px 24px 20px; }
        .viewer { background: #000; border: 1px solid #333; overflow: hidden; border-radius: 8px; }
        .viewer img { display: block; width: 100%; height: auto; }
        
        .panel { margin-top: 18px; padding: 16px 0 0 0; }
        .controls { display: grid; grid-template-columns: repeat(2, minmax(240px, 1fr)); gap: 18px 28px; align-items: end; }
        .control-group { min-width: 0; transition: opacity 0.3s; }
        .control-label { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; font-size: 14px; color: #d8d8d8; }
        .control-value { color: #a9a9a9; font-variant-numeric: tabular-nums; }
        .slider { width: 100%; margin: 0; }
        
        .toggle-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; font-size: 15px; color: #e5e5e5; }
        .switch { position: relative; display: inline-block; width: 52px; height: 30px; flex: 0 0 auto; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider-ui { position: absolute; cursor: pointer; inset: 0; background: #444; transition: 0.2s; border-radius: 999px; border: 1px solid #555; }
        .slider-ui:before { position: absolute; content: ""; height: 22px; width: 22px; left: 3px; top: 3px; background: #ddd; transition: 0.2s; border-radius: 50%; }
        .switch input:checked + .slider-ui { background: #2f6feb; border-color: #2f6feb; }
        .switch input:checked + .slider-ui:before { transform: translateX(22px); }
        
        /* New Radio Buttons for Modes */
        .radio-toolbar { display: flex; gap: 10px; margin-bottom: 24px; border-bottom: 1px solid #333; padding-bottom: 20px; flex-wrap: wrap; }
        .radio-toolbar input[type="radio"] { opacity: 0; position: fixed; width: 0; }
        .radio-toolbar label { flex: 1; text-align: center; background-color: #2d2d2d; padding: 12px 20px; font-size: 15px; font-weight: 500; border: 1px solid #444; border-radius: 8px; cursor: pointer; color: #aaa; transition: 0.2s; }
        .radio-toolbar label:hover { background-color: #3b3b3b; }
        .radio-toolbar input[type="radio"]:checked + label { background-color: #2f6feb; border-color: #2f6feb; color: white; }
        
        .disabled-panel { opacity: 0.4; pointer-events: none; filter: grayscale(100%); }
        
        .buttons { display: flex; gap: 12px; align-items: center; margin-top: 28px; flex-wrap: wrap; }
        button, a.capture { appearance: none; border: 1px solid #444; border-radius: 8px; padding: 12px 20px; font-size: 14px; font-weight: 500; cursor: pointer; color: white; background: #2d2d2d; text-decoration: none; text-align: center; }
        button:hover, a.capture:hover { background: #3b3b3b; }
        .btn-apply { background: #2f6feb; border-color: #2f6feb; flex: 1; }
        .btn-apply:hover { background: #2458c2; }
        .btn-capture { border-color: #059669; background: #059669; flex: 1; }
        .btn-capture:hover { background: #047857; }
        .btn-reset { margin-left: auto; border-color: #7f1d1d; background: #450a0a; color: #fecaca; }
        .btn-reset:hover { background: #7f1d1d; }
        
        .footer { margin-top: 18px; color: #999; font-size: 13px; font-variant-numeric: tabular-nums; }
        @media (max-width: 720px) { .controls { grid-template-columns: 1fr; } .buttons { flex-direction: column; align-items: stretch; } .btn-reset { margin-left: 0; } }
    </style>
</head>
<body>
    <header>ASTRA</header>

    <div class="container">
        <div class="viewer">
            <img id="liveStream" src="{{ url_for('video_feed') }}" alt="Astra live feed">
        </div>

        <form class="panel" method="post" action="{{ url_for('settings') }}" id="settingsForm">
            
            <div class="radio-toolbar">
                <input type="radio" id="mode_track" name="track_mode" value="1" {% if track_mode %}checked{% endif %}>
                <label for="mode_track">Track Mode (Auto)</label>

                <input type="radio" id="mode_manual" name="track_mode" value="0" {% if not track_mode %}checked{% endif %}>
                <label for="mode_manual">Manual Mode</label>
            </div>

            <div class="controls">
                <div class="control-group">
                    <div class="toggle-row">
                        <span>Horizontal Flip</span>
                        <label class="switch">
                            <input type="checkbox" name="hflip" {% if hflip %}checked{% endif %}>
                            <span class="slider-ui"></span>
                        </label>
                    </div>
                </div>

                <div class="control-group">
                    <div class="toggle-row">
                        <span>Vertical Flip</span>
                        <label class="switch">
                            <input type="checkbox" name="vflip" {% if vflip %}checked{% endif %}>
                            <span class="slider-ui"></span>
                        </label>
                    </div>
                </div>
                
                <div class="control-group">
                    <div class="control-label">
                        <span>Hardware Sensor Zoom</span>
                        <span class="control-value">{{ "%.1f"|format(sensor_zoom) }}x</span>
                    </div>
                    <input class="slider" type="range" name="sensor_zoom" min="1.0" max="4.0" step="0.5" value="{{ sensor_zoom }}">
                </div>

                <!-- These controls are visually disabled during Track Mode -->
                <div class="control-group {% if track_mode %}disabled-panel{% endif %}">
                    <div class="control-label">
                        <span>Brightness</span>
                        <span class="control-value">{{ "%.2f"|format(brightness) }}</span>
                    </div>
                    <input class="slider" type="range" name="brightness" min="-1.0" max="1.0" step="0.05" value="{{ brightness }}">
                </div>

                <div class="control-group {% if track_mode %}disabled-panel{% endif %}">
                    <div class="control-label">
                        <span>Exposure (µs)</span>
                        <span class="control-value">{{ exposure_us }}</span>
                    </div>
                    <input class="slider" type="range" name="exposure_us" min="100" max="2000000" step="1000" value="{{ exposure_us }}">
                </div>

                <div class="control-group {% if track_mode %}disabled-panel{% endif %}">
                    <div class="control-label">
                        <span>Gain</span>
                        <span class="control-value">{{ "%.2f"|format(gain) }}</span>
                    </div>
                    <input class="slider" type="range" name="gain" min="1.0" max="16.0" step="0.1" value="{{ gain }}">
                </div>
            </div>

            <div class="buttons">
                <button type="submit" class="btn-apply">Apply Adjustments</button>
                <a class="capture btn-capture" href="{{ url_for('capture') }}" target="_blank" download>⛶ Capture Frame</a>
                <button type="submit" formaction="{{ url_for('reset') }}" class="btn-reset">Reset Defaults</button>
            </div>

            <div class="footer">
                1920 × 1080 &nbsp;&nbsp;•&nbsp;&nbsp; 15 FPS
            </div>
        </form>
    </div>

    <script>
        // Visually update sliders before submitting
        document.querySelectorAll('.slider').forEach(slider => {
            slider.addEventListener('input', function() {
                const valSpan = this.parentElement.querySelector('.control-value');
                if (valSpan) {
                    if (this.name === 'gain' || this.name === 'brightness' || this.name === 'sensor_zoom') {
                        valSpan.innerText = parseFloat(this.value).toFixed(2) + (this.name === 'sensor_zoom' ? 'x' : '');
                    } else {
                        valSpan.innerText = this.value;
                    }
                }
            });
        });

        // Auto-submit form when toggling Track/Manual modes for quick UX
        document.querySelectorAll('input[name="track_mode"]').forEach(radio => {
            radio.addEventListener('change', function() {
                document.getElementById('settingsForm').submit();
            });
        });
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    with state_lock:
        hflip = camera_settings["hflip"]
        vflip = camera_settings["vflip"]
        track_mode = camera_settings["track_mode"]
        exposure_us = camera_settings["exposure_us"]
        gain = camera_settings["gain"]
        brightness = camera_settings["brightness"]
        sensor_zoom = camera_settings["sensor_zoom"]

    return render_template_string(
        INDEX_HTML,
        hflip=hflip,
        vflip=vflip,
        track_mode=track_mode,
        exposure_us=exposure_us,
        gain=gain,
        brightness=brightness,
        sensor_zoom=sensor_zoom
    )

@app.route("/video_feed")
def video_feed():
    return Response(
        mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )

@app.route("/settings", methods=["POST"])
def settings():
    hflip = "hflip" in request.form
    vflip = "vflip" in request.form
    track_mode = request.form.get("track_mode") == "1"
    
    exposure_us = clamp_int(request.form.get("exposure_us"), 100, 2000000, 50000)
    gain = clamp_float(request.form.get("gain"), 1.0, 16.0, 4.0)
    brightness = clamp_float(request.form.get("brightness"), -1.0, 1.0, 0.0)
    sensor_zoom = clamp_float(request.form.get("sensor_zoom"), 1.0, 4.0, 1.0)

    with state_lock:
        camera_settings["hflip"] = hflip
        camera_settings["vflip"] = vflip
        camera_settings["track_mode"] = track_mode
        camera_settings["exposure_us"] = exposure_us
        camera_settings["gain"] = gain
        camera_settings["brightness"] = brightness
        camera_settings["sensor_zoom"] = sensor_zoom

    restart_event.set()
    return redirect(url_for("index"))

@app.route("/reset", methods=["POST"])
def reset():
    with state_lock:
        camera_settings.update(DEFAULTS)
    
    restart_event.set()
    return redirect(url_for("index"))

@app.route("/capture")
def capture():
    with frame_cond:
        frame = latest_frame

    if frame is None:
        return "No frame available yet. Wait a second and try again.", 503

    filename = datetime.now().strftime("astra_%Y%m%d_%H%M%S.jpg")
    fileobj = BytesIO(frame)
    fileobj.seek(0)

    return send_file(
        fileobj,
        mimetype="image/jpeg",
        as_attachment=True,
        download_name=filename,
    )

def cleanup():
    stop_event.set()
    restart_event.set()

    try:
        if camera_proc and camera_proc.poll() is None:
            camera_proc.send_signal(signal.SIGINT)
            try:
                camera_proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                camera_proc.terminate()
    except Exception:
        pass

atexit.register(cleanup)

threading.Thread(target=camera_worker, daemon=True).start()

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=80)