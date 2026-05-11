#!/usr/bin/env python3
"""Create/check a local receiver virtualenv and install QRFT dependencies."""

import argparse
import os
import subprocess
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
REQ_FILE = ROOT / "requirements-receiver.txt"
REQUIRED_MODULES = {
    "cv2": "opencv-python",
    "numpy": "numpy",
    "requests": "requests",
    "urllib3": "urllib3",
}


def venv_python():
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def run(cmd):
    print("+ {}".format(" ".join(str(part) for part in cmd)))
    subprocess.check_call([str(part) for part in cmd])


def create_venv():
    if venv_python().exists():
        return
    print("creating virtualenv at {}".format(VENV_DIR))
    venv.EnvBuilder(with_pip=True, clear=False).create(VENV_DIR)


def missing_modules(python):
    code = "\n".join(
        [
            "import importlib.util, json",
            "mods = {}".format(repr(sorted(REQUIRED_MODULES))),
            "print(json.dumps([m for m in mods if importlib.util.find_spec(m) is None]))",
        ]
    )
    out = subprocess.check_output([str(python), "-c", code], text=True)
    import json

    return json.loads(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="print the full Python environment report")
    args = ap.parse_args()

    create_venv()
    python = venv_python()
    missing = missing_modules(python)
    if missing:
        packages = sorted({REQUIRED_MODULES[name] for name in missing})
        print("missing modules: {}".format(", ".join(missing)))
        run([python, "-m", "pip", "install", "--upgrade", "pip"])
        if REQ_FILE.exists():
            run([python, "-m", "pip", "install", "-r", REQ_FILE])
        else:
            run([python, "-m", "pip", "install", *packages])
    else:
        print("receiver dependencies already installed")
    if args.report:
        run([python, "check_python_env.py"])


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
