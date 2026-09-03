from flask import Flask, Response, request, jsonify
from picamera2 import Picamera2
import io
import time

app = Flask(__name__)

camera = Picamera2()
camera.configure(
    camera.create_still_configuration(
        main={"size": (1920, 1080), "format": "RGB888"}
    )
)
camera.start()
time.sleep(2)

# Hold the latest image in memory
latest_image_bytes = None


def capture_latest():
    global latest_image_bytes
    stream = io.BytesIO()
    camera.capture_file(stream, format="jpeg")
    latest_image_bytes = stream.getvalue()


# Take an initial image so the page isn't empty on first load
capture_latest()


@app.route("/")
def index():
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Pi Camera Snap</title>
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
      max-height: 70vh;
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
    input[type="text"] {
      padding: 0.5rem 0.75rem;
      font-size: 1rem;
      border-radius: 6px;
      border: 1px solid #444;
      background: #222;
      color: #eee;
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
    button:hover {
      background: #1d4ed8;
    }
    .status {
      margin-top: 0.5rem;
      font-size: 0.9rem;
      color: #aaa;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>Pi Camera Snap</h1>
    <img id="photo" src="/latest.jpg" alt="Latest photo">
    <div class="controls">
      <input id="cmd" type="text" placeholder='Type "snap" and press Enter' />
      <button id="snapBtn">Take Photo</button>
    </div>
    <div class="status" id="status">Ready.</div>
  </div>

  <script>
    const img = document.getElementById("photo");
    const cmd = document.getElementById("cmd");
    const status = document.getElementById("status");
    const snapBtn = document.getElementById("snapBtn");

    function takeSnap() {
      status.textContent = "Taking photo...";
      fetch("/snap", { method: "POST" })
        .then(r => r.json())
        .then(data => {
          if (data.ok) {
            // Force browser to fetch a fresh image
            img.src = "/latest.jpg?t=" + Date.now();
            status.textContent = "Photo taken.";
            cmd.value = "";
          } else {
            status.textContent = "Error: " + data.error;
          }
        })
        .catch(err => {
          status.textContent = "Error contacting server.";
          console.error(err);
        });
    }

    snapBtn.addEventListener("click", takeSnap);

    cmd.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const val = cmd.value.trim().toLowerCase();
        if (val === "snap") {
          takeSnap();
        } else {
          status.textContent = 'Type "snap" and press Enter.';
        }
      }
    });
  </script>
</body>
</html>"""


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


@app.route("/snap", methods=["POST"])
def snap():
    # Only take a new photo when this endpoint is called
    try:
        capture_latest()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, threaded=True)