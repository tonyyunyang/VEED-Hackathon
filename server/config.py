import os
from dotenv import load_dotenv

load_dotenv()

STORAGE_DIR = os.path.join(os.path.dirname(__file__), "storage")
ENABLE_LIPSYNC = os.getenv("ENABLE_LIPSYNC", "false").lower() == "true"
FAL_KEY = os.getenv("FAL_KEY", "")
LIPSYNC_RESOLUTION = os.getenv("LIPSYNC_RESOLUTION", "480p")
FRAME_SUBSAMPLE = int(os.getenv("FRAME_SUBSAMPLE", "5"))
