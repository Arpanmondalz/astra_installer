(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const view = $("view");
  const overlay = $("overlay");
  const statusPill = $("status");
  const footer = $("footer");

  let limits = null;
  let settings = null;
  let applying = false;
  let snapshotTimer = null;
  let seq = 0;

  const TARGET_INTERVAL_MS = 110;

  // --- helpers --------------------------------------------------------------

  const logToLinear = (value, [lo, hi]) =>
    Math.round((1000 * Math.log(value / lo)) / Math.log(hi / lo));

  const linearToLog = (slider, [lo, hi]) =>
    Math.round(lo * Math.pow(hi / lo, slider / 1000));

  function formatExposure(us) {
    if (us >= 1e6) return (us / 1e6).toFixed(2) + " s";
    if (us >= 1000) return (us / 1000).toFixed(1) + " ms";
    return us + " \u00b5s";
  }

  function debounce(fn, wait) {
    let timer = null;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), wait);
    };
  }

  function setDisabled(id, disabled) {
    const el = $(id);
    if (el) el.classList.toggle("disabled", disabled);
  }

  // --- server communication -------------------------------------------------

  async function send(path, body) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  }

  const pushControls = debounce(async (patch) => {
    try {
      applying = true;
      render(await send("/api/controls", patch));
    } catch (err) {
      console.error(err);
    } finally {
      applying = false;
    }
  }, 120);

  function change(key, value) {
    if (applying) return;
    settings[key] = value;
    pushControls({ [key]: value });
  }

  // --- rendering ------------------------------------------------------------

  function renderStatus(status) {
    const stale = status.frame_age === null || status.frame_age > 5;
    let cls = "pill pill-ok";
    let text = "live";

    if (status.state === "error") {
      cls = "pill pill-bad";
      text = "camera error";
    } else if (status.state === "stalled") {
      cls = "pill pill-bad";
      text = "restarting";
    } else if (status.state !== "running" || stale) {
      cls = "pill pill-wait";
      text = "waiting";
    }

    statusPill.className = cls;
    statusPill.textContent = text;

    const showOverlay = status.state === "error" || status.frame_age === null;
    overlay.hidden = !showOverlay;
    if (showOverlay) {
      overlay.textContent = status.error
        ? "Camera error: " + status.error
        : "Waiting for the camera\u2026";
    }

    footer.textContent = [
      status.stream_size.join(" \u00d7 "),
      status.fps.toFixed(1) + " fps",
      "stills " + status.still_size.join(" \u00d7 "),
    ].join("   \u2022   ");
  }

  function render(payload) {
    settings = payload.settings;
    limits = payload.limits;

    const exposure = $("exposure_us");
    exposure.value = logToLinear(settings.exposure_us, limits.exposure_us);
    $("exposure_us_val").textContent = formatExposure(settings.exposure_us);

    const gain = $("gain");
    [gain.min, gain.max] = limits.gain;
    gain.value = settings.gain;
    $("gain_val").textContent = settings.gain.toFixed(1) + "\u00d7";

    const ev = $("ev");
    [ev.min, ev.max] = limits.ev;
    ev.value = settings.ev;
    $("ev_val").textContent = (settings.ev > 0 ? "+" : "") + settings.ev.toFixed(1);

    const zoom = $("zoom");
    [zoom.min, zoom.max] = limits.zoom;
    zoom.value = settings.zoom;
    $("zoom_val").textContent = settings.zoom.toFixed(1) + "\u00d7";

    $("red_gain").value = settings.red_gain;
    $("red_gain_val").textContent = settings.red_gain.toFixed(2);
    $("blue_gain").value = settings.blue_gain;
    $("blue_gain_val").textContent = settings.blue_gain.toFixed(2);

    for (const key of ["auto_exposure", "mono", "hflip", "vflip", "awb_auto"]) {
      $(key).checked = settings[key];
    }
    $("metering").value = settings.metering;

    setDisabled("group_exposure", settings.auto_exposure);
    setDisabled("group_gain", settings.auto_exposure);
    setDisabled("group_red", settings.awb_auto);
    setDisabled("group_blue", settings.awb_auto);

    renderStatus(payload.status);
  }

  function renderPresets(list) {
    const bar = $("presets");
    bar.textContent = "";
    for (const preset of list) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn";
      button.textContent = preset.label;
      button.addEventListener("click", async () => {
        try {
          render(await send("/api/preset/" + encodeURIComponent(preset.id)));
        } catch (err) {
          console.error(err);
        }
      });
      bar.appendChild(button);
    }
  }

  // --- preview transports ---------------------------------------------------

  function stopSnapshots() {
    clearTimeout(snapshotTimer);
    snapshotTimer = null;
  }

  function startSnapshots() {
    stopSnapshots();
    const tick = () => {
      const started = performance.now();
      const probe = new Image();
      probe.onload = () => {
        view.src = probe.src;
        overlay.hidden = true;
        const elapsed = performance.now() - started;
        snapshotTimer = setTimeout(tick, Math.max(0, TARGET_INTERVAL_MS - elapsed));
      };
      probe.onerror = () => {
        snapshotTimer = setTimeout(tick, 1000);
      };
      probe.src = "/frame.jpg?s=" + seq++;
    };
    tick();
  }

  function setTransport(useMjpeg) {
    if (useMjpeg) {
      stopSnapshots();
      view.src = "/stream.mjpg?s=" + seq++;
    } else {
      view.src = "";
      startSnapshots();
    }
    try {
      localStorage.setItem("astra.mjpeg", useMjpeg ? "1" : "0");
    } catch (err) {
      /* private mode */
    }
  }

  // --- wiring ---------------------------------------------------------------

  function download(url) {
    const link = document.createElement("a");
    link.href = url;
    link.download = "";
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  function bind() {
    $("exposure_us").addEventListener("input", (event) => {
      const us = linearToLog(Number(event.target.value), limits.exposure_us);
      $("exposure_us_val").textContent = formatExposure(us);
      change("exposure_us", us);
    });

    const simple = {
      gain: (v) => v.toFixed(1) + "\u00d7",
      ev: (v) => (v > 0 ? "+" : "") + v.toFixed(1),
      zoom: (v) => v.toFixed(1) + "\u00d7",
      red_gain: (v) => v.toFixed(2),
      blue_gain: (v) => v.toFixed(2),
    };
    for (const [key, format] of Object.entries(simple)) {
      $(key).addEventListener("input", (event) => {
        const value = Number(event.target.value);
        $(key + "_val").textContent = format(value);
        change(key, value);
      });
    }

    for (const key of ["auto_exposure", "mono", "hflip", "vflip", "awb_auto"]) {
      $(key).addEventListener("change", (event) => change(key, event.target.checked));
    }
    $("metering").addEventListener("change", (event) => change("metering", event.target.value));

    $("mjpeg").addEventListener("change", (event) => setTransport(event.target.checked));

    $("capture").addEventListener("click", () => download("/capture"));

    $("capture_full").addEventListener("click", async (event) => {
      const button = event.target;
      button.disabled = true;
      button.textContent = "Capturing\u2026";
      try {
        download("/capture?full=1");
        // The sensor mode switch takes a moment; avoid a double trigger.
        await new Promise((resolve) => setTimeout(resolve, 4000));
      } finally {
        button.disabled = false;
        button.textContent = "Capture full 5 MP";
      }
    });

    $("reset").addEventListener("click", async () => {
      render(await send("/api/preset/reset"));
    });
  }

  async function refreshStatus() {
    try {
      const response = await fetch("/api/state", { cache: "no-store" });
      const payload = await response.json();
      if (!applying) render(payload);
      else renderStatus(payload.status);
    } catch (err) {
      statusPill.className = "pill pill-bad";
      statusPill.textContent = "offline";
    }
  }

  async function init() {
    const response = await fetch("/api/state", { cache: "no-store" });
    const payload = await response.json();
    renderPresets(payload.presets);
    render(payload);
    bind();

    let useMjpeg = false;
    try {
      useMjpeg = localStorage.getItem("astra.mjpeg") === "1";
    } catch (err) {
      /* private mode */
    }
    $("mjpeg").checked = useMjpeg;
    setTransport(useMjpeg);

    setInterval(refreshStatus, 3000);
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) stopSnapshots();
      else if (!$("mjpeg").checked) startSnapshots();
    });
  }

  init().catch((err) => {
    console.error(err);
    overlay.hidden = false;
    overlay.textContent = "Could not reach the Astra server.";
  });
})();
