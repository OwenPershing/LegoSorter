import io
import time
from flask import Flask, Response
from picamera2 import Picamera2

app = Flask(__name__)

camera = Picamera2()
camera.configure(
    camera.create_video_configuration(
        main={"size": (1280, 720), "format": "RGB888"}
    )
)
camera.start()
time.sleep(2)


def generate_frames():
    while True:
        frame = io.BytesIO()
        camera.capture_file(frame, format="jpeg")

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + frame.getvalue()
            + b"\r\n"
        )


@app.route("/")
def camera_page():
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Raspberry Pi Camera</title>
  <style>
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #111;
    }
    img {
      max-width: 100vw;
      max-height: 100vh;
    }
  </style>
</head>
<body>
  <img src="/stream" alt="Live Raspberry Pi camera feed">
</body>
</html>"""


@app.route("/stream")
def stream():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)