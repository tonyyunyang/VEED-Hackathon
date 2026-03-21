"""
Configuration — all values come from environment variables with sensible defaults.
"""

import os
import platform
from dotenv import load_dotenv

load_dotenv()

# ── Paths ────────────────────────────────────────────────────────────────

STORAGE_DIR = os.path.join(os.path.dirname(__file__), "storage")
PICTURE_LIBRARY_DIR = os.path.join(os.path.dirname(__file__), "picture_example")

# ── Face detection ───────────────────────────────────────────────────────

FRAME_SUBSAMPLE = int(os.getenv("FRAME_SUBSAMPLE", "5"))
DUMMY_TRACKING = os.getenv("DUMMY_TRACKING", "true").lower() == "true"

# ── FaceFusion API ───────────────────────────────────────────────────────

FACEFUSION_API_URL = os.getenv("FACEFUSION_API_URL", "http://localhost:8001")
FACEFUSION_SWAP_MODEL = os.getenv("FACEFUSION_SWAP_MODEL", "hyperswap_1a_256")
FACEFUSION_PIXEL_BOOST = os.getenv("FACEFUSION_PIXEL_BOOST", "512x512")
FACEFUSION_ENHANCER = os.getenv("FACEFUSION_ENHANCER", "true").lower() == "true"
FACEFUSION_EXECUTION_PROVIDER = os.getenv(
    "FACEFUSION_EXECUTION_PROVIDER",
    "coreml" if platform.system() == "Darwin" else "cpu",
)
FACEFUSION_VIDEO_QUALITY = int(os.getenv("FACEFUSION_VIDEO_QUALITY", "90"))
FACEFUSION_THREAD_COUNT = int(os.getenv("FACEFUSION_THREAD_COUNT", "4"))

# ── Post-processing ─────────────────────────────────────────────────────

ENABLE_LIPSYNC = os.getenv("ENABLE_LIPSYNC", "true").lower() == "true"
