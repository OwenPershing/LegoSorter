from picamera2 import Picamera2
from libcamera import controls
from flask import Flask, Response, render_template_string, request, jsonify
import io
import threading
import time

app = Flask(__name__)

camera = Picamera2()
camera.configure(
    camera.create_video_configuration(
        main={"size": (1280, 720), "format": "RGB888"}
    )
)
camera.start()

# Start in manual focus
camera.set_controls({"AfMode": controls.AfModeEnum.Manual, "LensPosition": 0.0})

min_focus, max_focus, _ = camera.camera_controls["LensPosition"]

# For MJPEG streaming
frame_lock = threading.Lock()
latest_frame = None


def capture_loop():
    global latest_frame
    while True:
        stream = io.BytesIO()
        camera.capture_file(stream, format="jpeg")
        with frame_lock:
            latest_frame = stream.getvalue()
        time.sleep(0.1)  # ~10 FPS


threading.Thread(target=capture_loop, daemon=True).start()


HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Live Focus Test</title>
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
      max-height: 65vh;
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
  </style>
</head>
<body>
  <h1>Live Focus Test</h1>
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
  </div>
  <div class="info" id="info">Ready.</div>

  <script>
    const lpInput = document.getElementById("lp");
    const info = document.getElementById("info");

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
    while True:
        with frame_lock:
            if latest_frame is not None:
                return Response(
                    latest_frame,
                    mimetype="image/jpeg",
                    headers={
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "Expires": "0",
                    },
                )
        time.sleep(0.05)


@app.route("/set_focus", methods=["POST"])
def set_focus():
    data = request.get_json()
    mode = data.get("mode")
    try:
        if mode == "manual":
            lp = float(data.get("lens_position", 0))
            camera.set_controls({
                "AfMode": controls.AfModeEnum.Manual,
                "LensPosition": lp,
            })
            return jsonify({"ok": True})
        elif mode == "single":
            camera.set_controls({
                "AfMode": controls.AfModeEnum.Auto,
                "AfTrigger": controls.AfTriggerEnum.Start,
            })
            return jsonify({"ok": True})
        elif mode == "continuous":
            camera.set_controls({
                "AfMode": controls.AfModeEnum.Continuous,
            })
            return jsonify({"ok": True})
        elif mode == "cancel":
            camera.set_controls({
                "AfMode": controls.AfModeEnum.Manual,
            })
            return jsonify({"ok": True})
        else:
            return jsonify({"ok": False, "error": "Unknown mode"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8003, threaded=True)