from flask import Flask, Response
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
time.sleep(2)  # let camera warm up


@app.route("/")
def snap():
    # Capture a fresh frame to memory (no file on disk)
    stream = io.BytesIO()
    camera.capture_file(stream, format="jpeg")
    data = stream.getvalue()

    return Response(
        data,
        mimetype="image/jpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, threaded=True)