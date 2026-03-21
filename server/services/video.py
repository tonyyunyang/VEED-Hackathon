"""
Video utilities — frame extraction via ffmpeg/ffprobe.

FaceFusion handles all video encoding/decoding for the swap itself.
This module is only used during the face-detection step to extract
individual JPEG frames for InsightFace analysis.
"""

import os
import subprocess
import json


def get_video_info(video_path: str) -> dict:
    """Probe a video file and return {"fps": float, "total_frames": int}."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-select_streams", "v:0", video_path],
        capture_output=True, text=True, check=True,
    )
    stream = json.loads(result.stdout)["streams"][0]

    num, den = map(int, stream["r_frame_rate"].split("/"))
    fps = num / den if den else 30.0

    total_frames = int(stream.get("nb_frames", 0))
    if total_frames == 0:
        total_frames = int(float(stream.get("duration", 0)) * fps)

    return {"fps": fps, "total_frames": total_frames}


def extract_frames(video_path: str, output_dir: str) -> dict:
    """Extract every frame as frame_0001.jpg, frame_0002.jpg, … Return video info."""
    os.makedirs(output_dir, exist_ok=True)
    info = get_video_info(video_path)
    subprocess.run(
        ["ffmpeg", "-i", video_path, "-vsync", "0",
         os.path.join(output_dir, "frame_%04d.jpg"), "-y"],
        capture_output=True, check=True,
    )
    return info
