import os
import subprocess
import json


def get_video_info(video_path: str) -> dict:
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-select_streams", "v:0", video_path
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
    return {"fps": fps, "total_frames": nb_frames}


def extract_frames(video_path: str, output_dir: str) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    info = get_video_info(video_path)
    cmd = [
        "ffmpeg", "-i", video_path, "-vsync", "0",
        os.path.join(output_dir, "frame_%04d.jpg"), "-y"
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return info


def extract_audio(video_path: str, output_path: str) -> bool:
    cmd = [
        "ffmpeg", "-i", video_path, "-vn", "-acodec", "aac",
        "-b:a", "128k", output_path, "-y"
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
    frames_dir: str, audio_path: str | None, output_path: str, fps: float
) -> None:
    cmd = [
        "ffmpeg", "-framerate", str(fps),
        "-i", os.path.join(frames_dir, "frame_%04d.jpg"),
    ]
    if audio_path and os.path.exists(audio_path):
        cmd.extend(["-i", audio_path, "-c:a", "aac", "-shortest"])
    cmd.extend([
        "-vf", "crop=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v", "libx264", 
        "-pix_fmt", "yuv420p", 
        output_path, 
        "-y"
    ])
    subprocess.run(cmd, capture_output=True, check=True)
