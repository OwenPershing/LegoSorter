from picamera2 import Picamera2
from libcamera import controls
from flask import Flask, Response, render_template_string, request, jsonify
import io
import time
import requests
import threading
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

camera = Picamera2()

# Use a modest resolution and a video-style config for stability
camera.configure(
    camera.create_video_configuration(
        main={"size": (1280, 720), "format": "RGB888"},
        queue=False,  # simpler pipeline
    )
)
camera.start()

# Start in manual focus
camera.set_controls({"AfMode": controls.AfModeEnum.Manual, "LensPosition": 0.0})

min_focus, max_focus, _ = camera.camera_controls["LensPosition"]

# Brickognize endpoint
BRICKOGNIZE_URL = "https://api.brickognize.com/predict/"

# Simple frame buffer for MJPEG
frame_lock = threading.Lock()
latest_frame = None


def capture_loop():
    global latest_frame
    stream = io.BytesIO()
    while True:
        try:
            stream.seek(0)
            camera.capture_file(stream, format="jpeg")
            data = stream.getvalue()
            with frame_lock:
                latest_frame = data
        except Exception as e:
            logger.warning("Capture error: %s", e)
        # Small delay to keep the pipeline happy
        time.sleep(0.05)


threading.Thread(target=capture_loop, daemon=True).start()


def generate_mjpeg():
    while True:
        with frame_lock:
            if latest_frame is not None:
                yield (
                    b"--FRAME\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + latest_frame
                    + b"\r\n"
                )
        time.sleep(0.03)


HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Live Focus + Lego ID</title>
  <style>
    body {
      background: #111;
      color: #eee;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      text-align: center;
      margin: 0;
      padding: 1rem;
    }
    img {
      max-width: 95vw;
      max-height: 55vh;
      border: 1px solid #333;
      background: #000;
    }
    .controls {
      margin-top: 0.75rem;
      display: flex;
      gap: 0.5rem;
      justify-content: center;
      align-items: center;
      flex-wrap: wrap;
    }
    input[type=number] {
      width: 90px;
      padding: 4px 6px;
      background: #222;
      color: #eee;
      border: 1px solid #444;
      border-radius: 4px;
    }
    button {
      padding: 6px 12px;
      background: #2563eb;
      color: #fff;
      border: none;
      border-radius: 4px;
      cursor: pointer;
    }
    button:hover {
      background: #1d4ed8;
    }
    button:disabled {
      background: #555;
      cursor: not-allowed;
    }
    .info {
      margin-top: 0.5rem;
      font-size: 0.9rem;
      color: #aaa;
    }
    .results {
      margin-top: 1rem;
      text-align: left;
      max-width: 900px;
      margin-left: auto;
      margin-right: auto;
    }
    .result-item {
      border: 1px solid #333;
      background: #1a1a1a;
      padding: 0.5rem;
      margin-bottom: 0.75rem;
      border-radius: 6px;
    }
    .result-part {
      font-weight: bold;
      color: #60a5fa;
      margin-bottom: 0.25rem;
    }
    .result-conf {
      color: #fbbf24;
      margin-top: 0.25rem;
    }
    .colors-title {
      margin-top: 0.5rem;
      font-size: 0.85rem;
      color: #ccc;
    }
    .color-item {
      display: inline-block;
      margin: 0.25rem 0.5rem 0.25rem 0;
      padding: 0.2rem 0.4rem;
      border-radius: 4px;
      border: 1px solid #444;
      font-size: 0.85rem;
    }
    a {
      color: #60a5fa;
      text-decoration: none;
    }
    a:hover {
      text-decoration: underline;
    }
  </style>
</head>
<body>
  <h1>Live Focus + Lego ID</h1>
  <img id="view" src="/feed" alt="Live camera feed">
  <div class="controls">
    <label>
      LensPosition:
      <input id="lp" type="number" step="0.1" min="{{min_lp}}" max="{{max_lp}}" value="0">
    </label>
    <button id="setBtn">Set Manual</button>
    <button id="afSingleBtn">Single AF</button>
    <button id="afContBtn">Continuous AF</button>
    <button id="afCancelBtn">Cancel AF</button>
    <button id="legoBtn">Get Lego</button>
  </div>
  <div class="info" id="info">Ready.</div>
  <div class="results" id="results"></div>

  <script>
    const lpInput = document.getElementById("lp");
    const info = document.getElementById("info");
    const resultsDiv = document.getElementById("results");
    const legoBtn = document.getElementById("legoBtn");

    function postJson(url, data) {
      return fetch(url, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data),
      }).then(r => r.json());
    }

    document.getElementById("setBtn").onclick = () => {
      const lp = parseFloat(lpInput.value);
      postJson("/set_focus", {lens_position: lp, mode: "manual"})
        .then(d => {
          info.textContent = d.ok ? "Manual focus set." : ("Error: " + d.error);
        });
    };

    document.getElementById("afSingleBtn").onclick = () => {
      postJson("/set_focus", {mode: "single"})
        .then(d => {
          info.textContent = d.ok ? "Single autofocus triggered." : ("Error: " + d.error);
        });
    };

    document.getElementById("afContBtn").onclick = () => {
      postJson("/set_focus", {mode: "continuous"})
        .then(d => {
          info.textContent = d.ok ? "Continuous autofocus enabled." : ("Error: " + d.error);
        });
    };

    document.getElementById("afCancelBtn").onclick = () => {
      postJson("/set_focus", {mode: "cancel"})
        .then(d => {
          info.textContent = d.ok ? "Autofocus cancelled." : ("Error: " + d.error);
        });
    };

    legoBtn.addEventListener("click", () => {
      legoBtn.disabled = true;
      info.textContent = "Identifying Lego...";
      resultsDiv.innerHTML = "";

      fetch("/identify_lego", { method: "POST" })
        .then(r => r.json())
        .then(data => {
          legoBtn.disabled = false;
          if (data.ok) {
            info.textContent = "Identification complete.";
            if (!data.predictions || data.predictions.length === 0) {
              resultsDiv.innerHTML = "<div class='info'>No predictions returned.</div>";
              return;
            }
            let html = "";
            data.predictions.forEach(p => {
              const link = p.bricklink_url
                ? `<a href="${p.bricklink_url}" target="_blank">BrickLink</a>`
                : "";

              let colorsHtml = "";
              if (p.colors && p.colors.length > 0) {
                colorsHtml = "<div class='colors-title'>Colors:</div>";
                p.colors.forEach(c => {
                  const name = c.name || "Unknown";
                  const score = ((c.score || 0) * 100).toFixed(1);
                  colorsHtml += `<span class='color-item'>${name} (${score}%)</span>`;
                });
              }

              html += `<div class='result-item'>
                <div class='result-part'>Part: ${p.id} ${link ? "(" + link + ")" : ""}</div>
                <div>Name: ${p.name}</div>
                <div>Category: ${p.category}</div>
                <div class='result-conf'>Score: ${(p.score * 100).toFixed(1)}%</div>
                ${colorsHtml}
              </div>`;
            });
            resultsDiv.innerHTML = html;
          } else {
            info.textContent = "Error: " + (data.error || "Unknown error");
          }
        })
        .catch(err => {
          legoBtn.disabled = false;
          info.textContent = "Error contacting server.";
          console.error(err);
        });
    });
  </script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(
        HTML.replace("{{min_lp}}", str(min_focus)).replace("{{max_lp}}", str(max_focus))
    )


@app.route("/feed")
def feed():
    return Response(
        generate_mjpeg(),
        mimetype="multipart/x-mixed-replace; boundary=FRAME",
    )


@app.route("/set_focus", methods=["POST"])
def set_focus():
    data = request.get_json()
    mode = data.get("mode")
    try:
        if mode == "manual":
            lp = float(data.get("lens_position", 0))
            # Give the pipeline a moment before changing controls
            time.sleep(0.1)
            camera.set_controls({
                "AfMode": controls.AfModeEnum.Manual,
                "LensPosition": lp,
            })
            return jsonify({"ok": True})
        elif mode == "single":
            time.sleep(0.1)
            camera.set_controls({
                "AfMode": controls.AfModeEnum.Auto,
                "AfTrigger": controls.AfTriggerEnum.Start,
            })
            return jsonify({"ok": True})
        elif mode == "continuous":
            time.sleep(0.1)
            camera.set_controls({
                "AfMode": controls.AfModeEnum.Continuous,
            })
            return jsonify({"ok": True})
        elif mode == "cancel":
            time.sleep(0.1)
            camera.set_controls({
                "AfMode": controls.AfModeEnum.Manual,
            })
            return jsonify({"ok": True})
        else:
            return jsonify({"ok": False, "error": "Unknown mode"}), 400
    except Exception as e:
        logger.exception("Focus error")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/identify_lego", methods=["POST"])
def identify_lego():
    try:
        # Capture current frame to memory
        stream = io.BytesIO()
        camera.capture_file(stream, format="jpeg")
        image_bytes = stream.getvalue()

        # Send to Brickognize with color enabled
        files = {
            "query_image": ("image.jpg", image_bytes, "image/jpeg")
        }
        params = {
            "predict_color": "true",
            "top_k_items": 5,
            "top_k_colors": 5,
            "min_similarity_items": 0.5,
            "min_similarity_colors": 0.2,
        }

        resp = requests.post(
            BRICKOGNIZE_URL,
            params=params,
            files=files,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        # Parse items and colors from response
        items = data.get("items") or []
        predictions = []
        for item in items:
            bricklink_url = None
            for site in (item.get("external_sites") or []):
                if site.get("name") == "bricklink":
                    bricklink_url = site.get("url")
                    break

            colors = []
            for c in (item.get("colors") or []):
                colors.append({
                    "name": c.get("name", "Unknown"),
                    "score": float(c.get("score", 0)),
                })

            predictions.append({
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "category": item.get("category", ""),
                "score": float(item.get("score", 0)),
                "bricklink_url": bricklink_url,
                "colors": colors,
            })

        return jsonify({"ok": True, "predictions": predictions})

    except Exception as e:
        logger.exception("Identify error")
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8003, threaded=True)