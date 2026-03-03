/**
 * Audio Steganography - Frontend Logic
 * Handles Encode/Decode forms, tab switching, and fetch API calls.
 */

(function () {
    "use strict";

    const API_BASE = ""; // Same origin

    // --- Tab switching ---
    const tabs = document.querySelectorAll(".tab");
    const panels = document.querySelectorAll(".panel");

    tabs.forEach((tab) => {
        tab.addEventListener("click", () => {
            const targetId = tab.dataset.tab;
            tabs.forEach((t) => t.classList.remove("active"));
            panels.forEach((p) => p.classList.remove("active"));
            tab.classList.add("active");
            document.getElementById(`${targetId}-section`).classList.add("active");
            // Clear any visible errors when switching
            clearMessages(targetId);
        });
    });

    function clearMessages(section) {
        const errEl = document.getElementById(`${section}-error`);
        const successEl = document.getElementById(`${section}-success`);
        if (errEl) {
            errEl.classList.add("hidden");
            errEl.textContent = "";
        }
        if (successEl) successEl.classList.add("hidden");
    }

    function showError(section, message) {
        const el = document.getElementById(`${section}-error`);
        const successEl = document.getElementById(`${section}-success`);
        if (successEl) successEl.classList.add("hidden");
        if (el) {
            el.textContent = message;
            el.classList.remove("hidden");
        }
    }

    function showSuccess(section) {
        const el = document.getElementById(`${section}-success`);
        const errEl = document.getElementById(`${section}-error`);
        if (errEl) errEl.classList.add("hidden");
        if (el) el.classList.remove("hidden");
    }

    function setLoading(buttonId, loading) {
        const btn = document.getElementById(buttonId);
        if (!btn) return;
        if (loading) {
            btn.classList.add("loading");
            btn.disabled = true;
        } else {
            btn.classList.remove("loading");
            btn.disabled = false;
        }
    }

    // --- Encode form ---
    const encodeForm = document.getElementById("encode-form");
    if (encodeForm) {
        encodeForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            clearMessages("encode");

            const audioInput = document.getElementById("encode-audio");
            const imageInput = document.getElementById("encode-image");

            if (!audioInput.files.length || !imageInput.files.length) {
                showError("encode", "Please select both an audio file and an image file.");
                return;
            }

            const formData = new FormData();
            formData.append("audio", audioInput.files[0]);
            formData.append("image", imageInput.files[0]);

            setLoading("encode-btn", true);

            try {
                const res = await fetch(`${API_BASE}/encode`, {
                    method: "POST",
                    body: formData
                });

                const contentType = res.headers.get("content-type");
                const isJson = contentType && contentType.includes("application/json");

                if (!res.ok) {
                    if (isJson) {
                        const data = await res.json();
                        showError("encode", data.error || "Encoding failed.");
                    } else {
                        showError("encode", `Server error: ${res.status}`);
                    }
                    return;
                }

                if (isJson) {
                    const data = await res.json();
                    showError("encode", data.error || "Encoding failed.");
                    return;
                }

                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = "encoded_audio.wav";
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);

                showSuccess("encode");
            } catch (err) {
                showError("encode", err.message || "Network error. Please try again.");
            } finally {
                setLoading("encode-btn", false);
            }
        });
    }

    // --- Decode form ---
    const decodeForm = document.getElementById("decode-form");
    if (decodeForm) {
        decodeForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            clearMessages("decode");

            const audioInput = document.getElementById("decode-audio");

            if (!audioInput.files.length) {
                showError("decode", "Please select an encoded audio file.");
                return;
            }

            const formData = new FormData();
            formData.append("audio", audioInput.files[0]);

            setLoading("decode-btn", true);

            try {
                const res = await fetch(`${API_BASE}/decode`, {
                    method: "POST",
                    body: formData
                });

                const contentType = res.headers.get("content-type");
                const isJson = contentType && contentType.includes("application/json");

                if (!res.ok) {
                    if (isJson) {
                        const data = await res.json();
                        showError("decode", data.error || "Decoding failed.");
                    } else {
                        showError("decode", `Server error: ${res.status}`);
                    }
                    return;
                }

                if (isJson) {
                    const data = await res.json();
                    showError("decode", data.error || "Decoding failed.");
                    return;
                }

                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = "extracted_image.png";
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);

                showSuccess("decode");
            } catch (err) {
                showError("decode", err.message || "Network error. Please try again.");
            } finally {
                setLoading("decode-btn", false);
            }
        });
    }
})();
