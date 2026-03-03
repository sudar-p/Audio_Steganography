"""
Steganography Module: Audio LSB encoding with multi-stage compression.

Handles hiding images inside WAV audio files using Least Significant Bit modification.
Compression pipeline (in order):
  1. RLE (lossless) - for images with uniform regions
  2. zlib (lossless) - additional 2-3x on already-compressible data
  3. JPEG (lossy) - high compression (20-50x) for photographic images
  4. Downscale + JPEG - when even JPEG doesn't fit, resize then compress

Target: fit ~8MB images into ~1MB audio using 4 LSBs per sample
       (4x capacity ≈ 262KB) + aggressive JPEG/downscale (~32x compression).
"""

import struct
import io
import wave
import zlib
from typing import Tuple
import numpy as np
from PIL import Image


# Magic signature to identify our steganographic payload
MAGIC = b"STEG"
MAGIC_LEN = 4

# Header format: magic(4) + format(1) + width(4) + height(4) + channels(1) = 14 bytes
# format: 0=raw, 1=RLE, 2=RLE+zlib, 3=JPEG, 4=downscaled JPEG (scale in channels byte when format=4)
HEADER_LEN = 14

FORMAT_RAW = 0
FORMAT_RLE = 1
FORMAT_RLE_ZLIB = 2
FORMAT_JPEG = 3
FORMAT_JPEG_DOWNSCALED = 4

# Bits per sample for LSB encoding: 4 = 4x capacity (8MB image in 1MB audio with ~32x compression)
BITS_PER_SAMPLE = 4


def _get_audio_params(wav_data: bytes) -> Tuple[object, bytes, int, int]:
    """
    Parse WAV file and return (params, frames_bytes, n_samples, sampwidth).
    """
    wav_io = io.BytesIO(wav_data)
    with wave.open(wav_io, "rb") as wav:
        params = wav.getparams()
        frames = wav.readframes(wav.getnframes())
        n_samples = wav.getnframes() * wav.getnchannels()
        sampwidth = wav.getsampwidth()
        return params, frames, n_samples, sampwidth


def _get_audio_capacity(wav_data: bytes) -> int:
    """
    Calculate the number of bytes we can hide in a WAV file using LSB encoding.
    Uses BITS_PER_SAMPLE bits per sample. Capacity = (n_samples * BITS_PER_SAMPLE) / 8 bytes.
    With 4 bits/sample: 1MB audio ≈ 262KB payload (fits 8MB image at ~32x compression).
    """
    _, _, n_samples, _ = _get_audio_params(wav_data)
    return (n_samples * BITS_PER_SAMPLE) // 8


def _rle_compress_pixels(pixels: np.ndarray) -> bytes:
    """
    Run-Length Encoding on pixel data.
    Format: For each run of identical pixels: [R, G, B, (A), count]
    Count is stored as 1 byte (1-255). For runs > 255, we split into multiple entries.
    Achieves ~99%+ lossless reconstruction for images with uniform regions.
    """
    flat = pixels.flatten()
    result = bytearray()
    i = 0
    channels = pixels.shape[-1] if len(pixels.shape) > 2 else 1

    while i < len(flat):
        # Count consecutive identical values (pixel = channels values)
        count = 0
        start = i
        chunk_size = channels
        while i + chunk_size <= len(flat):
            match = True
            for c in range(chunk_size):
                if flat[i + c] != flat[start + c]:
                    match = False
                    break
            if not match:
                break
            count += 1
            i += chunk_size
            if count >= 255:  # Max count per run (1 byte)
                break

        # Write pixel values + count
        for c in range(chunk_size):
            result.append(flat[start + c] & 0xFF)
        result.append(count)

    return bytes(result)


def _rle_decompress_pixels(data: bytes, width: int, height: int, channels: int) -> np.ndarray:
    """
    Reverse RLE to reconstruct pixel array.
    """
    pixels = []
    i = 0
    chunk_size = channels + 1  # R, G, B, (A), count

    while i + chunk_size <= len(data) and len(pixels) < width * height * channels:
        pixel_vals = [data[i + c] for c in range(channels)]
        count = data[i + channels]
        i += chunk_size
        for _ in range(count):
            pixels.extend(pixel_vals)

    arr = np.array(pixels, dtype=np.uint8)
    # Reshape to (height, width, channels)
    expected = height * width * channels
    if len(arr) < expected:
        arr = np.pad(arr, (0, expected - len(arr)), mode="constant", constant_values=0)
    arr = arr[:expected]
    return arr.reshape((height, width, channels))


def _raw_pixels_to_bytes(pixels: np.ndarray) -> bytes:
    """Convert raw pixel array to bytes (no compression)."""
    return pixels.tobytes()


def _bytes_to_raw_pixels(data: bytes, width: int, height: int, channels: int) -> np.ndarray:
    """Convert raw bytes back to pixel array."""
    expected = height * width * channels
    arr = np.frombuffer(data[:expected], dtype=np.uint8)
    if len(arr) < expected:
        arr = np.pad(arr, (0, expected - len(arr)), mode="constant", constant_values=0)
    return arr.reshape((height, width, channels))


def _lsb_encode(audio_bytes: bytes, payload: bytes) -> bytes:
    """
    Embed payload into audio using BITS_PER_SAMPLE LSBs of each sample.
    4 bits/sample gives 4x capacity for fitting 8MB images in 1MB audio.
    """
    params, frames, n_samples, sampwidth = _get_audio_params(audio_bytes)
    frame_array = np.frombuffer(frames, dtype=np.uint8).copy()

    bits = BITS_PER_SAMPLE
    capacity_bits = n_samples * bits
    payload_bits = []
    for b in payload:
        for i in range(8):
            payload_bits.append((b >> (7 - i)) & 1)
    if len(payload_bits) > capacity_bits:
        raise ValueError(
            f"Payload ({len(payload)} bytes) exceeds audio LSB capacity "
            f"({capacity_bits // 8} bytes)."
        )

    # For 16-bit LE: sample bytes are [lo, hi]. LSBs are in lo (bits 0..3 for 4-bit).
    mask_clear = (1 << bits) - 1  # 0x0F for 4 bits
    mask_keep = 0xFF & ~mask_clear  # keep upper bits, clear lower
    for i in range(0, min(len(payload_bits), capacity_bits), bits):
        byte_idx = (i // bits) * sampwidth
        val = 0
        for j in range(bits):
            if i + j < len(payload_bits):
                val |= payload_bits[i + j] << (bits - 1 - j)
        frame_array[byte_idx] = (frame_array[byte_idx] & mask_keep) | (val & mask_clear)

    out_io = io.BytesIO()
    with wave.open(out_io, "wb") as wav_out:
        wav_out.setparams(params)
        wav_out.writeframes(frame_array.tobytes())

    return out_io.getvalue()


def _lsb_decode(audio_bytes: bytes, num_bytes: int) -> bytes:
    """Extract payload from BITS_PER_SAMPLE LSBs of each audio sample."""
    _, frames, n_samples, sampwidth = _get_audio_params(audio_bytes)
    frame_array = np.frombuffer(frames, dtype=np.uint8)

    bits = BITS_PER_SAMPLE
    mask = (1 << bits) - 1
    result = bytearray()
    bit_buffer = 0
    bit_count = 0
    max_bits = min(num_bytes * 8, n_samples * bits)

    for i in range(0, max_bits, bits):
        sample_idx = i // bits
        byte_idx = sample_idx * sampwidth
        val = frame_array[byte_idx] & mask
        for j in range(bits):
            if i + j >= max_bits:
                break
            bit = (val >> (bits - 1 - j)) & 1
            bit_buffer = (bit_buffer << 1) | bit
            bit_count += 1
            if bit_count == 8:
                result.append(bit_buffer & 0xFF)
                bit_buffer = 0
                bit_count = 0
                if len(result) >= num_bytes:
                    return bytes(result)

    return bytes(result)


def _image_to_jpeg_bytes(img: Image.Image, quality: int) -> bytes:
    """Convert image to JPEG bytes at given quality (1-95)."""
    out = io.BytesIO()
    img.convert("RGB").save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue()


def _compress_to_fit(
    img: Image.Image, capacity: int
) -> Tuple[bytes, int, int, int, int]:
    """
    Apply aggressive multi-stage compression to fit image within capacity.
    Returns: (data, width, height, channels, format)
    """
    img = img.convert("RGB")
    pixels = np.array(img)
    height, width, channels = pixels.shape
    raw_size = width * height * channels

    # Reserve space for header
    available = capacity - HEADER_LEN
    if available <= 0:
        raise ValueError("Audio capacity too small even for header.")

    # 1. Try RLE (lossless)
    rle_data = _rle_compress_pixels(pixels)
    if len(rle_data) <= available:
        # Try RLE + zlib for even more compression
        zlib_data = zlib.compress(rle_data, level=9)
        if len(zlib_data) <= available:
            return zlib_data, width, height, channels, FORMAT_RLE_ZLIB
        return rle_data, width, height, channels, FORMAT_RLE

    # 2. JPEG with decreasing quality (target 24-32x for 8MB in 1MB audio)
    for quality in [50, 35, 25, 15, 10, 7, 5, 3, 2, 1]:
        jpeg_data = _image_to_jpeg_bytes(img, quality)
        if len(jpeg_data) <= available:
            return jpeg_data, width, height, channels, FORMAT_JPEG

    # 3. Downscale + JPEG (aggressive for 8MB in 1MB audio: up to 100x)
    for scale in [0.5, 0.4, 0.33, 0.25, 0.2, 0.15, 0.1]:
        new_w = max(1, int(width * scale))
        new_h = max(1, int(height * scale))
        small = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        for quality in [25, 15, 10, 7, 5, 3, 2, 1]:
            jpeg_data = _image_to_jpeg_bytes(small, quality)
            if len(jpeg_data) <= available:
                return jpeg_data, new_w, new_h, channels, FORMAT_JPEG_DOWNSCALED

    raise ValueError(
        f"Cannot compress image to fit. Need {min(raw_size, len(rle_data))} bytes, "
        f"audio has {available} bytes. Use longer audio or smaller image."
    )


def _bytes_to_image(
    data: bytes, width: int, height: int, channels: int, compressed: bool
) -> Image.Image:
    """Reconstruct PIL Image from bytes."""
    if compressed:
        pixels = _rle_decompress_pixels(data, width, height, channels)
    else:
        pixels = _bytes_to_raw_pixels(data, width, height, channels)
    return Image.fromarray(pixels, "RGB")


def encode(audio_data: bytes, image_data: bytes, image_format: str = "PNG") -> bytes:
    """
    Hide image inside audio file using LSB steganography.
    Uses aggressive multi-stage compression (RLE, zlib, JPEG, downscale+JPEG)
    to fit large images (e.g. 3MB) into small audio (e.g. 1MB).

    Args:
        audio_data: Raw WAV file bytes
        image_data: Raw image file bytes (PNG/JPG)
        image_format: "PNG" or "JPEG"

    Returns:
        Modified WAV bytes with hidden image

    Raises:
        ValueError: If capacity insufficient even after compression, or invalid input
    """
    img = Image.open(io.BytesIO(image_data))
    capacity = _get_audio_capacity(audio_data)

    payload_bytes, width, height, channels, fmt = _compress_to_fit(img, capacity)

    # Build header: magic(4) + format(1) + width(4) + height(4) + channels(1) = 14
    header = (
        MAGIC
        + struct.pack("B", fmt)
        + struct.pack(">I", width)
        + struct.pack(">I", height)
        + struct.pack("B", channels)
    )
    full_payload = header + payload_bytes

    if len(full_payload) > capacity:
        raise ValueError(
            f"Image (after compression: {len(full_payload)} bytes) exceeds "
            f"audio capacity ({capacity} bytes). Use a longer audio file or smaller image."
        )

    return _lsb_encode(audio_data, full_payload)


def decode(audio_data: bytes) -> Tuple[bytes, str]:
    """
    Extract hidden image from encoded audio.
    Supports formats: raw, RLE, RLE+zlib, JPEG, downscaled JPEG.

    Args:
        audio_data: WAV bytes that contain hidden image

    Returns:
        (image_bytes, format) - format is "PNG" for output

    Raises:
        ValueError: If no valid payload found
    """
    header_bytes = _lsb_decode(audio_data, HEADER_LEN)
    if len(header_bytes) < HEADER_LEN:
        raise ValueError("Audio file too short or not a valid steganographic payload.")

    magic = header_bytes[:MAGIC_LEN]
    if magic != MAGIC:
        raise ValueError(
            "No steganographic payload found. File may not contain a hidden image."
        )

    fmt = header_bytes[4]
    width = struct.unpack(">I", header_bytes[5:9])[0]
    height = struct.unpack(">I", header_bytes[9:13])[0]
    channels = header_bytes[13]

    capacity = _get_audio_capacity(audio_data)
    data_len = capacity - HEADER_LEN
    total_len = HEADER_LEN + data_len
    full_payload = _lsb_decode(audio_data, total_len)
    payload_data = full_payload[HEADER_LEN:HEADER_LEN + data_len]

    if fmt in (FORMAT_JPEG, FORMAT_JPEG_DOWNSCALED):
        # Payload is JPEG bytes - truncate at EOI marker to remove LSB padding
        eoi = payload_data.find(b"\xff\xd9")
        if eoi != -1:
            payload_data = payload_data[: eoi + 2]
        img = Image.open(io.BytesIO(payload_data))
        img = img.convert("RGB")
    elif fmt == FORMAT_RLE_ZLIB:
        rle_data = zlib.decompress(payload_data)
        pixels = _rle_decompress_pixels(rle_data, width, height, channels)
        img = Image.fromarray(pixels, "RGB")
    elif fmt == FORMAT_RLE:
        pixels = _rle_decompress_pixels(payload_data, width, height, channels)
        img = Image.fromarray(pixels, "RGB")
    elif fmt == FORMAT_RAW:
        pixels = _bytes_to_raw_pixels(payload_data, width, height, channels)
        img = Image.fromarray(pixels, "RGB")
    else:
        raise ValueError(f"Unknown payload format: {fmt}")

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue(), "PNG"
