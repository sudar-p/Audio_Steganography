# Audio Steganography Web Application

Hide images inside WAV audio files using LSB (Least Significant Bit) steganography with multi-stage compression. Supports fitting large images (e.g. 8MB) into small audio files (e.g. 1MB).

## Features

- **Encode**: Hide PNG/JPG images inside WAV audio files
- **Decode**: Extract hidden images from encoded WAV files
- **Multi-stage compression**: RLE → RLE+zlib → JPEG → downscale+JPEG (automatic)
- **High capacity**: 4 LSBs per sample (~4x capacity) for fitting 8MB images in 1MB audio
- **Audio integrity**: Minimal perceptual change to the audio

## Quick Start

```bash
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

## Usage

1. **Encode**: Upload a WAV file (cover) and PNG/JPG (secret). Click "Encode & Download" to get the modified audio.
2. **Decode**: Upload the encoded WAV file to extract and download the hidden image.

## File Structure

```
sudar/
├── app.py              # Flask backend (encode/decode endpoints)
├── steganography.py    # Core LSB + compression logic
├── requirements.txt    # Python dependencies
├── README.md
├── PROJECT_REFERENCE.txt
└── static/
    ├── index.html
    ├── style.css
    └── script.js
```

## Requirements

- **Audio**: WAV format only (uncompressed; MP3/OGG would destroy the payload)
- **Images**: PNG or JPG
- **Python**: 3.8+

## Technical Overview

- **Method**: LSB steganography (4 bits per audio sample)
- **Compression**: RLE, zlib, JPEG, downscale+JPEG (chosen automatically to fit capacity)
- **Target**: 8MB image in 1MB audio (~32x compression)
