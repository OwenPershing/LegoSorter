from flask import Flask, Response, request, jsonify, render_template_string
from picamera2 import Picamera2
import io
import time
import requests

app = Flask(__name__)

# ----- CONFIGURE THIS -----
# Brickognize API base URL – check https://api.brickognize.com/docs
BRICKOGNIZE_URL = "https://api.brickognize.com/v1/predict"  # example; adjust if docs differ
# If they require a key, add headers like:
# BRICKOGNIZE_HEADERS = {"Authorization": "Bearer YOUR_KEY"}
BRICKOGNIZE_HEADERS = {}
# --------------------------

camera = Picamera2()
camera.configure(
    camera.create_still_configuration(
        main={"size": (1920, 1080), "format": "RGB888"}
    )
)
camera.start()
time.sleep(2)

latest_image_bytes = None


def capture_latest():
    global latest_image_bytes
    stream = io.BytesIO()
    camera.capture_file(stream, format="jpeg")
    latest_image_bytes = stream.getvalue()


# Initial image so page isn't empty
capture_latest()


HTML_PAGE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>LEGO Brick Identifier</title>
  <style>
    body {
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #111;
      color: #eee;
      display: grid;
      place-items: center;
      min-height: 100vh;
    }
    .container {
      width: min(95vw, 900px);
      text-align: center;
    }
    img {
      max-width: 100%;
      max-height: 60vh;
      border: 1px solid #333;
      background: #000;
    }
    .controls {
      margin-top: 1rem;
      display: flex;
      gap: 0.5rem;
      justify-content: center;
      align-items: center;
      flex-wrap: wrap;
    }
    button {
      padding: 0.5rem 1rem;
      font-size: 1rem;
      border-radius: 6px;
      border: none;
      background: #2563eb;
      color: #fff;
      cursor: pointer;
    }
    button:disabled {
      background: #555;
      cursor: not-allowed;
    }
    .status {
      margin-top: 0.5rem;
      font-size: 0.9rem;
      color: #aaa;
      white-space: pre-wrap;
      text-align: left;
      max-width: 100%;
      overflow-x: auto;
    }
    .results {
      margin-top: 1rem;
      text-align: left;
    }
    .result-item {
      border: 1px solid #333;
      background: #1a1a1a;
      padding: 0.5rem;
      margin-bottom: 0.5rem;
      border-radius: 6px;
    }
    .result-part {
      font-weight: bold;
      color: #60a5fa;
    }
    .result-conf {
      color: #fbbf24;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>LEGO Brick Identifier</h1>
    <img id="photo" src="/latest.jpg" alt="Latest photo">
    <div class="controls">
      <button id="identifyBtn">Take Photo & Identify</button>
    </div>
    <div class="status" id="status">Ready.</div>
    <div class="results" id="results"></div>
  </div>

  <script>
    const img = document.getElementById("photo");
    const status = document.getElementById("status");
    const resultsDiv = document.getElementById("results");
    const identifyBtn = document.getElementById("identifyBtn");

    identifyBtn.addEventListener("click", () => {
      identifyBtn.disabled = true;
      status.textContent = "Taking photo...";
      resultsDiv.innerHTML = "";

      fetch("/identify", { method: "POST" })
        .then(r => r.json())
        .then(data => {
          identifyBtn.disabled = false;
          if (data.ok) {
            // Refresh image
            img.src = "/latest.jpg?t=" + Date.now();
            status.textContent = "Identification complete.";
            if (!data.predictions || data.predictions.length === 0) {
              resultsDiv.innerHTML = "<div class='status'>No predictions returned.</div>";
              return;
            }
            let html = "";
            data.predictions.forEach(p => {
              html += `<div class='result-item'>
                <div class='result-part'>Part: ${p.part || "Unknown"}</div>
                <div>Name: ${p.name || "Unknown"}</div>
                <div class='result-conf'>Confidence: ${(p.confidence * 100).toFixed(1)}%</div>
              </div>`;
            });
            resultsDiv.innerHTML = html;
          } else {
            status.textContent = "Error: " + (data.error || "Unknown error");
          }
        })
        .catch(err => {
          identifyBtn.disabled = false;
          status.textContent = "Error contacting server.";
          console.error(err);
        });
    });
  </script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML_PAGE)


@app.route("/latest.jpg")
def latest():
    if latest_image_bytes is None:
        return "No image yet", 503
    return Response(
        latest_image_bytes,
        mimetype="image/jpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.route("/identify", methods=["POST"])
def identify():
    global latest_image_bytes
    try:
        # 1. Capture new image
        capture_latest()

        # 2. Send to Brickognize
        files = {"file": ("image.jpg", latest_image_bytes, "image/jpeg")}
        resp = requests.post(
            BRICKOGNIZE_URL,
            headers=BRICKOGNIZE_HEADERS,
            files=files,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        # Adapt this to the actual JSON structure Brickognize returns.
        # Common pattern: list of predictions with part id/name/score.
        predictions = []
        if isinstance(data, list):
            for item in data[:5]:  # top 5
                # Adjust field names to match docs
                part = item.get("part") or item.get("part_id") or item.get("id", "")
                name = item.get("name") or item.get("description", "")
                conf = float(item.get("score") or item.get("confidence") or item.get("prob", 0))
                predictions.append({"part": part, "name": name, "confidence": conf})
        elif isinstance(data, dict):
            # If they wrap predictions in a key like 'predictions'
            raw = data.get("predictions") or data.get("results") or []
            for item in raw[:5]:
                part = item.get("part") or item.get("part_id") or item.get("id", "")
                name = item.get("name") or item.get("description", "")
                conf = float(item.get("score") or item.get("confidence") or item.get("prob", 0))
                predictions.append({"part": part, "name": name, "confidence": conf})

        return jsonify({"ok": True, "predictions": predictions})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8002, threaded=True)