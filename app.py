"""
Flask Backend for Audio-Image Steganography Web Application.

Provides /encode and /decode endpoints for hiding images in WAV audio
and extracting them, with full error handling and in-memory file processing.
"""

import io
from flask import Flask, request, jsonify, send_file, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge

from steganography import encode as steg_encode, decode as steg_decode

app = Flask(__name__, static_folder="static", static_url_path="")

# Max upload size: 50MB for audio, 10MB for image (adjust as needed)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

# Allowed file extensions
ALLOWED_AUDIO = {"wav"}
ALLOWED_IMAGE = {"png", "jpg", "jpeg"}


def _allowed_file(filename: str, extensions: set) -> bool:
    """Check if filename has an allowed extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in extensions


def _get_extension(filename: str) -> str:
    """Return lowercase extension."""
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


@app.route("/")
def index():
    """Serve the main HTML page."""
    return send_from_directory(app.static_folder, "index.html")


@app.route("/encode", methods=["POST"])
def encode_endpoint():
    """
    Encode endpoint: Accepts audio (WAV) and image (PNG/JPG), returns modified WAV.

    Form fields:
        - audio: WAV file
        - image: PNG or JPG file

    Returns:
        - On success: WAV file (application/octet-stream)
        - On error: JSON with 'error' key
    """
    if "audio" not in request.files or "image" not in request.files:
        return jsonify({"error": "Both audio and image files are required."}), 400

    audio_file = request.files["audio"]
    image_file = request.files["image"]

    if audio_file.filename == "" or image_file.filename == "":
        return jsonify({"error": "Please select both an audio file and an image file."}), 400

    if not _allowed_file(audio_file.filename, ALLOWED_AUDIO):
        return jsonify({
            "error": "Audio file must be in WAV format. Other formats (MP3, etc.) "
                     "cause compression artifacts that destroy the hidden payload."
        }), 400

    if not _allowed_file(image_file.filename, ALLOWED_IMAGE):
        return jsonify({
            "error": "Image must be in PNG or JPG/JPEG format."
        }), 400

    try:
        audio_data = audio_file.read()
        image_data = image_file.read()
    except Exception as e:
        return jsonify({"error": f"Failed to read uploaded files: {str(e)}"}), 500

    if len(audio_data) == 0:
        return jsonify({"error": "Audio file is empty."}), 400

    if len(image_data) == 0:
        return jsonify({"error": "Image file is empty."}), 400

    try:
        image_ext = _get_extension(image_file.filename)
        image_format = "PNG" if image_ext == "png" else "JPEG"
        encoded_audio = steg_encode(audio_data, image_data, image_format=image_format)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Encoding failed: {str(e)}"}), 500

    return send_file(
        io.BytesIO(encoded_audio),
        mimetype="audio/wav",
        as_attachment=True,
        download_name="encoded_audio.wav"
    )


@app.route("/decode", methods=["POST"])
def decode_endpoint():
    """
    Decode endpoint: Accepts encoded WAV, returns extracted image (PNG).

    Form fields:
        - audio: WAV file (previously encoded with our tool)

    Returns:
        - On success: PNG image (image/png)
        - On error: JSON with 'error' key
    """
    if "audio" not in request.files:
        return jsonify({"error": "Audio file is required."}), 400

    audio_file = request.files["audio"]

    if audio_file.filename == "":
        return jsonify({"error": "Please select an encoded audio file."}), 400

    if not _allowed_file(audio_file.filename, ALLOWED_AUDIO):
        return jsonify({
            "error": "File must be in WAV format."
        }), 400

    try:
        audio_data = audio_file.read()
    except Exception as e:
        return jsonify({"error": f"Failed to read uploaded file: {str(e)}"}), 500

    if len(audio_data) == 0:
        return jsonify({"error": "Audio file is empty."}), 400

    try:
        image_bytes, image_format = steg_decode(audio_data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Decoding failed: {str(e)}"}), 500

    return send_file(
        io.BytesIO(image_bytes),
        mimetype="image/png",
        as_attachment=True,
        download_name="extracted_image.png"
    )


@app.errorhandler(RequestEntityTooLarge)
def handle_too_large(e):
    """Handle file too large errors."""
    return jsonify({"error": "File(s) too large. Max 50MB total."}), 413


@app.errorhandler(413)
def handle_413(e):
    """Handle 413 Request Entity Too Large."""
    return jsonify({"error": "File(s) too large. Max 50MB total."}), 413


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
