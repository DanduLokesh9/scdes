"""Vendor the dictation runtime and model into the app.

Run once, offline. Everything the browser needs to transcribe speech is served
from this application's own origin — no CDN, no Hugging Face, no third-party
request at runtime.

That is the whole point. Chrome's built-in `webkitSpeechRecognition` sends audio
to Google, and a user two screens earlier signed a confidentiality agreement
covering these materials. An agency dictating its draft governance answers into
someone else's transcription service would contradict both the agreement and the
claim this product is built on.

What gets vendored, and why it is this much:

    transformers.min.js      0.9 MB   the JS runtime
    ort/*.wasm              ~10 MB    ONNX Runtime, the actual execution engine
    whisper-tiny.en          40 MB    encoder + decoder, quantised

Roughly 50 MB. Fetched once by the browser, on first use of the microphone —
never on page load, because first paint is under a second and this would undo
that. The deploy bundle excludes it; it is placed on the server once, like the
audit log and the agency data.

    python -m tools.fetch_speech
"""

from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEECH = ROOT / "app" / "web" / "assets" / "speech"
MODEL = SPEECH / "models" / "Xenova" / "whisper-tiny.en"

CDN = "https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2/dist"
HF = "https://huggingface.co/Xenova/whisper-tiny.en/resolve/main"

RUNTIME = ["transformers.min.js"]
#: Both the plain and SIMD builds. onnxruntime picks at load time by feature
#: detection, and shipping only one means a browser without SIMD gets a 404
#: rather than a slower transcription.
WASM = ["ort-wasm.wasm", "ort-wasm-simd.wasm"]
CONFIG = ["config.json", "preprocessor_config.json", "tokenizer.json",
          "tokenizer_config.json", "generation_config.json"]
ONNX = ["encoder_model_quantized.onnx", "decoder_model_merged_quantized.onnx"]


def fetch(url: str, target: Path) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "gaius-vendor"})
    with urllib.request.urlopen(request, timeout=600) as response, \
            target.open("wb") as out:
        shutil.copyfileobj(response, out)
    return target.stat().st_size


def main() -> int:
    total = 0
    plan = (
        [(f"{CDN}/{f}", SPEECH / f) for f in RUNTIME]
        + [(f"{CDN}/{f}", SPEECH / "ort" / f) for f in WASM]
        + [(f"{HF}/{f}", MODEL / f) for f in CONFIG]
        + [(f"{HF}/onnx/{f}", MODEL / "onnx" / f) for f in ONNX]
    )
    for url, target in plan:
        try:
            size = fetch(url, target)
        except Exception as exc:                            # noqa: BLE001
            # generation_config.json is absent from some model repos and the
            # runtime copes; anything else missing is worth knowing about.
            print(f"  skipped {target.name}: {type(exc).__name__}")
            continue
        total += size
        print(f"  {size / 1024 / 1024:7.1f} MB  "
              f"{target.relative_to(SPEECH).as_posix()}")

    print(f"\n  {total / 1024 / 1024:7.1f} MB  total, served from this app "
          f"and nowhere else")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
