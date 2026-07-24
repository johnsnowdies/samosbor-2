# ─────────────────────────────────────────────────
# Image Cropper — Flask-микросервис для обрезки AI-картинок
# Перенесён из v1 (2024)
# ─────────────────────────────────────────────────

from flask import Flask, request, send_file, Response
from PIL import Image
import requests
from io import BytesIO
import base64

app = Flask(__name__)


@app.route("/crop", methods=["GET"])
def crop_image():
    encoded_url = request.args.get("url")

    if not encoded_url:
        return Response("URL not provided", status=400)

    try:
        decoded_url = base64.urlsafe_b64decode(encoded_url).decode("utf-8")
    except Exception:
        return Response("Invalid URL encoding", status=400)

    try:
        response = requests.get(decoded_url)
        response.raise_for_status()
    except requests.RequestException:
        return Response(status=204)

    try:
        img = Image.open(BytesIO(response.content))
    except Exception:
        return Response("Unable to open image", status=400)

    width, height = img.size
    if height <= 68:
        return Response("Image height is too small to crop", status=400)

    # Обрезаем 68 пикселей снизу (водяной знак)
    cropped_img = img.crop((0, 0, width, height - 68))

    img_io = BytesIO()
    cropped_img.save(img_io, format=img.format)
    img_io.seek(0)

    return send_file(img_io, mimetype=f"image/{img.format.lower()}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)