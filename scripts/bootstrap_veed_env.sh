#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg must be installed and available on PATH before bootstrapping this repo." >&2
  exit 1
fi

"$PYTHON_BIN" -m ensurepip --upgrade >/dev/null 2>&1 || true
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -e "$ROOT_DIR/face-detect-track"
"$PYTHON_BIN" -m pip install -e "$ROOT_DIR/server"

if [[ -f "$ROOT_DIR/facefusion-VEED/facefusion.py" ]]; then
  "$PYTHON_BIN" "$ROOT_DIR/facefusion-VEED/facefusion.py" headless-run -h >/dev/null
  echo "Verified FaceFusion CLI in-place checkout: $ROOT_DIR/facefusion-VEED"
else
  echo "Warning: facefusion-VEED/facefusion.py was not found. The FaceFusion backend will stay unavailable until that repo exists locally." >&2
fi

echo "Installed VEED backend dependencies into: $("$PYTHON_BIN" -c 'import sys; print(sys.executable)')"
echo "Next steps:"
echo "  1. Copy .env.example to .env"
echo "  2. Set FACE_SWAPPER_BACKEND=facefusion if you want the FaceFusion backend"
echo "  3. Add reference source images under server/reference_faces/ or set FACE_SWAP_REFERENCE_IMAGE"
