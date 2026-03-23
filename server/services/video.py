import json
import logging
import os
import subprocess
from typing import Callable

import cv2

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def media_type_for_path(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    raise ValueError(f"Unsupported media extension: {ext}")


def output_image_extension_for_path(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in {".jpg", ".jpeg", ".png"}:
        return ext
    return ".png"


def get_video_info(video_path: str) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        "-select_streams",
        "v:0",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)
    stream = info["streams"][0]
    r_frame_rate = stream["r_frame_rate"]
    num, den = map(int, r_frame_rate.split("/"))
    fps = num / den if den else 30.0
    nb_frames = int(stream.get("nb_frames", 0))
    if nb_frames == 0:
        duration = float(stream.get("duration", 0))
        nb_frames = int(duration * fps)
    return {
        "fps": fps,
        "total_frames": nb_frames,
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "media_type": "video",
    }


def extract_frames(video_path: str, output_dir: str) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    info = get_video_info(video_path)
    logger.info(
        "extract_frames: %s → %s (%d total frames, %.1f fps)",
        video_path,
        output_dir,
        info.get("total_frames", 0),
        info.get("fps", 0),
    )
    cmd = [
        "ffmpeg",
        "-i",
        video_path,
        "-vsync",
        "0",
        os.path.join(output_dir, "frame_%04d.jpg"),
        "-y",
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    extracted = len(
        [
            f
            for f in os.listdir(output_dir)
            if f.startswith("frame_") and f.endswith(".jpg")
        ]
    )
    logger.info("extract_frames: done — %d frames written", extracted)
    return info


def stage_image_as_frames(image_path: str, output_dir: str) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    frame = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if frame is None:
        raise RuntimeError(f"Unable to read image: {image_path}")

    frame_path = os.path.join(output_dir, "frame_0001.jpg")
    if not cv2.imwrite(frame_path, frame):
        raise RuntimeError(f"Unable to stage image frame at {frame_path}")

    height, width = frame.shape[:2]
    return {
        "fps": 1.0,
        "total_frames": 1,
        "width": width,
        "height": height,
        "media_type": "image",
        "output_extension": output_image_extension_for_path(image_path),
    }


def extract_audio(video_path: str, output_path: str) -> bool:
    cmd = [
        "ffmpeg",
        "-i",
        video_path,
        "-vn",
        "-acodec",
        "aac",
        "-b:a",
        "128k",
        output_path,
        "-y",
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


def extract_audio_segment(
    video_path: str, output_path: str, start_time: float, duration: float
) -> bool:
    cmd = [
        "ffmpeg",
        "-ss",
        f"{max(0.0, start_time):.3f}",
        "-t",
        f"{max(0.0, duration):.3f}",
        "-i",
        video_path,
        "-vn",
        "-acodec",
        "aac",
        "-b:a",
        "128k",
        output_path,
        "-y",
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


def reassemble_video(
    frames_dir: str,
    audio_path: str | None,
    output_path: str,
    fps: float,
    progress_callback: Callable[[int, int], None] | None = None,
) -> None:
    # Count total frames so we can report progress
    total_frames = len(
        [
            f
            for f in os.listdir(frames_dir)
            if f.startswith("frame_") and f.endswith(".jpg")
        ]
    )
    logger.info(
        "reassemble_video: encoding %d frames at %.1f fps → %s",
        total_frames,
        fps,
        output_path,
    )

    cmd = [
        "ffmpeg",
        "-framerate",
        str(fps),
        "-i",
        os.path.join(frames_dir, "frame_%04d.jpg"),
    ]
    if audio_path and os.path.exists(audio_path):
        cmd.extend(["-i", audio_path, "-c:a", "aac", "-shortest"])
    cmd.extend(
        [
            "-vf",
            "crop=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-progress",
            "pipe:1",
            output_path,
            "-y",
        ]
    )

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    last_log_frame = 0
    output_lines: list[str] = []
    if process.stdout is not None:
        for line in process.stdout:
            output_lines.append(line.rstrip())
            if len(output_lines) > 50:
                output_lines.pop(0)
            # ffmpeg -progress outputs key=value lines, "frame=123"
            line = line.strip()
            if line.startswith("frame="):
                try:
                    current_frame = int(line.split("=", 1)[1])
                except ValueError:
                    continue
                if progress_callback and total_frames > 0:
                    progress_callback(current_frame, total_frames)
                if current_frame - last_log_frame >= max(1, total_frames // 10):
                    logger.info(
                        "reassemble_video: encoded %d/%d frames (%.0f%%)",
                        current_frame,
                        total_frames,
                        current_frame / max(1, total_frames) * 100,
                    )
                    last_log_frame = current_frame

    return_code = process.wait()
    if return_code != 0:
        tail = "\n".join(output_lines[-20:])
        logger.error(
            "reassemble_video: ffmpeg exited with code %d: %s", return_code, tail[-500:]
        )
        raise subprocess.CalledProcessError(return_code, cmd, stderr=tail)

    logger.info("reassemble_video: done — %d frames encoded", total_frames)


def write_image_output(frames_dir: str, output_path: str) -> None:
    frame_files = sorted(
        file_name
        for file_name in os.listdir(frames_dir)
        if file_name.startswith("frame_") and file_name.endswith(".jpg")
    )
    if not frame_files:
        raise RuntimeError(f"No rendered frames found in {frames_dir}")

    frame = cv2.imread(os.path.join(frames_dir, frame_files[0]), cv2.IMREAD_COLOR)
    if frame is None:
        raise RuntimeError(f"Unable to read rendered frame {frame_files[0]}")

    if not cv2.imwrite(output_path, frame):
        raise RuntimeError(f"Unable to write output image at {output_path}")
