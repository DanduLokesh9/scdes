"""Is the dictation runtime complete and self-contained?

Two things worth checking without a browser.

**Completeness.** `allowRemoteModels = false` means a missing file is a hard
error rather than a quiet fetch from Hugging Face — which is exactly the
behavior wanted, and exactly why an incomplete vendoring must be caught here
rather than by a user pressing the microphone.

**Self-containment.** The whole justification for 60 MB of local model is that
no audio and no request leaves the machine. If the vendored JavaScript still
points at a CDN, that justification is gone and the feature should not ship.

    python -m tools.check_speech
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEECH = ROOT / "app" / "web" / "assets" / "speech"
MODEL = SPEECH / "models" / "Xenova" / "whisper-tiny.en"

REQUIRED = [
    SPEECH / "transformers.min.js",
    SPEECH / "ort" / "ort-wasm.wasm",
    SPEECH / "ort" / "ort-wasm-simd.wasm",
    MODEL / "config.json",
    MODEL / "preprocessor_config.json",
    MODEL / "tokenizer.json",
    MODEL / "tokenizer_config.json",
    MODEL / "onnx" / "encoder_model_quantized.onnx",
    MODEL / "onnx" / "decoder_model_merged_quantized.onnx",
]


def main() -> int:
    print("files:")
    missing = []
    total = 0
    for path in REQUIRED:
        if path.is_file():
            total += path.stat().st_size
            print(f"  {path.stat().st_size / 1024 / 1024:7.1f} MB  "
                  f"{path.relative_to(SPEECH).as_posix()}")
        else:
            missing.append(path)
            print(f"  MISSING      {path.relative_to(SPEECH).as_posix()}")
    print(f"  {total / 1024 / 1024:7.1f} MB  total")

    print("\nstructure:")
    ok = not missing

    # ONNX files start with a protobuf field header; a truncated download is a
    # far likelier failure here than a corrupt one, and both look like a valid
    # file to the filesystem.
    for name in ("encoder_model_quantized.onnx",
                 "decoder_model_merged_quantized.onnx"):
        path = MODEL / "onnx" / name
        if not path.is_file():
            continue
        head = path.read_bytes()[:2]
        good = head[:1] == b"\x08"
        print(f"  {name:38} {'looks like ONNX' if good else 'NOT ONNX'}")
        ok = ok and good

    wasm = SPEECH / "ort" / "ort-wasm-simd.wasm"
    if wasm.is_file():
        magic = wasm.read_bytes()[:4] == b"\x00asm"
        print(f"  {'ort-wasm-simd.wasm':38} "
              f"{'valid WebAssembly' if magic else 'NOT WebAssembly'}")
        ok = ok and magic

    try:
        cfg = json.loads((MODEL / "config.json").read_text(encoding="utf-8"))
        print(f"  {'config.json':38} model_type={cfg.get('model_type')}")
    except Exception as exc:                                # noqa: BLE001
        print(f"  config.json unreadable: {exc}")
        ok = False

    print("\nself-contained:")
    js = (ROOT / "app" / "web" / "assets" / "speech.js").read_text(encoding="utf-8")
    # The client must never name an external host. The vendored bundle contains
    # CDN strings of its own as fallbacks, which is why env.allowRemoteModels
    # and the explicit wasmPaths matter — those are what stop it reaching for
    # them.
    hosts = re.findall(r"https?://[a-z0-9.\-]+", js)
    print(f"  external hosts in speech.js : {hosts or 'none'}")
    for needed in ("allowRemoteModels = false", "localModelPath",
                   "wasm.wasmPaths"):
        present = needed in js
        print(f"  {needed:29} : {'set' if present else 'MISSING'}")
        ok = ok and present

    print("\nnot in the deploy bundle:")
    push = (ROOT / "deploy" / "push.ps1").read_text(encoding="utf-8")
    excluded = "app\\web\\assets\\speech" in push
    print(f"  push.ps1 excludes it        : {excluded}")
    ok = ok and excluded and not hosts

    print(f"\n{'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
