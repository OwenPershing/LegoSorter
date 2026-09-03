from picamera2 import Picamera2
from libcamera import controls
from flask import Flask, Response, render_template_string, request, jsonify
import io

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

HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Focus Test</title>
  <style>
    body { background:#111; color:#eee; font-family:system-ui; text-align:center; }
    img { max-width:95vw; max-height:70vh; border:1px solid #333; }
    input[type=number] { width:80px; padding:4px; }
    button { padding:6px 12px; }
  </style>
</head>
<body>
  <h1>Focus Test</h1>
  <img id="view" src="/feed">
  <div>
    LensPosition:
    <input id="lp" type="number" step="0.1" min="{{min_lp}}" max="{{max_lp}}" value="0">
    <button id="setBtn">Set</button>
    <div id="info" style="margin-top:8px; color:#aaa;"></div>
  </div>

  <script>
    const lpInput = document.getElementById("lp");
    const info = document.getElementById("info");
    document.getElementById("setBtn").onclick = () => {
      const lp = parseFloat(lpInput.value);
      fetch("/set_focus", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({lens_position: lp})
      })
      .then(r=>r.json())
      .then(d => {
        info.textContent = d.ok ? "Focus set." : ("Error: " + d.error);
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
    stream = io.BytesIO()
    camera.capture_file(stream, format="jpeg")
    return Response(stream.getvalue(), mimetype="image/jpeg")


@app.route("/set_focus", methods=["POST"])
def set_focus():
    data = request.get_json()
    lp = float(data.get("lens_position", 0))
    try:
        camera.set_controls({"AfMode": controls.AfModeEnum.Manual, "LensPosition": lp})
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8003, threaded=True)