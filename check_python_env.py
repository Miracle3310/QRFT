#!/usr/bin/env python3
"""Check whether this machine can run the QR file-transfer tools.

This script is intentionally stdlib-only. Run it on both sides:

    python check_python_env.py

The encoder side only needs Python 3.8+ and usually tkinter.
The decoder side can optionally use numpy/opencv/Pillow/requests.
"""

import importlib.util
import json
import os
import platform
import sys
import traceback


def module_status(name):
    spec = importlib.util.find_spec(name)
    return {
        "available": spec is not None,
        "origin": getattr(spec, "origin", None) if spec is not None else None,
    }


def check_tkinter():
    result = {
        "available": False,
        "can_create_window": False,
        "screen": None,
        "error": None,
    }
    try:
        import tkinter as tk

        result["available"] = True
        root = tk.Tk()
        root.withdraw()
        result["can_create_window"] = True
        result["screen"] = {
            "width": root.winfo_screenwidth(),
            "height": root.winfo_screenheight(),
            "depth": root.winfo_screendepth(),
        }
        root.destroy()
    except Exception as exc:  # noqa: BLE001 - diagnostic script
        result["error"] = "{}: {}".format(type(exc).__name__, exc)
    return result


def main():
    optional_modules = [
        "numpy",
        "cv2",
        "PIL",
        "requests",
        "matplotlib",
        "imageio",
    ]
    stdlib_modules = [
        "tkinter",
        "zlib",
        "struct",
        "base64",
        "hashlib",
        "http.client",
        "urllib.request",
    ]

    report = {
        "python": {
            "version": sys.version,
            "version_info": list(sys.version_info[:5]),
            "executable": sys.executable,
            "prefix": sys.prefix,
            "platform": sys.platform,
            "architecture": platform.architecture(),
        },
        "cwd": os.getcwd(),
        "environment": {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
            "DISPLAY": os.environ.get("DISPLAY", ""),
        },
        "stdlib": {name: module_status(name) for name in stdlib_modules},
        "optional": {name: module_status(name) for name in optional_modules},
        "tkinter_runtime": check_tkinter(),
        "recommendation": {},
    }

    version_ok = sys.version_info >= (3, 8)
    encoder_ok = version_ok and report["tkinter_runtime"]["can_create_window"]
    decoder_nice = (
        report["optional"]["numpy"]["available"]
        and report["optional"]["cv2"]["available"]
    )

    report["recommendation"] = {
        "python_version_ok": version_ok,
        "stdlib_tk_encoder_ok": encoder_ok,
        "opencv_decoder_ok": decoder_nice,
        "encoder_summary": (
            "OK: stdlib tkinter fullscreen encoder should work"
            if encoder_ok
            else "Fallback recommended: use MATLAB encoder or HTML/canvas player"
        ),
        "decoder_summary": (
            "OK: OpenCV/numpy decoder path is available"
            if decoder_nice
            else "Install decoder dependencies on receiver: numpy opencv-python pillow requests"
        ),
    }

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - keep diagnostics visible
        traceback.print_exc()
        sys.exit(1)
