"""Tests for server/services/video.py — FFmpeg frame extraction and reassembly."""
import os
import sys
import shutil
import tempfile

import cv2
import numpy as np
import pytest

# Add server to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from services.video import (
    extract_audio,
    extract_frames,
    get_video_info,
    media_type_for_path,
    reassemble_video,
    stage_image_as_frames,
    write_image_output,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
TEST_VIDEO = os.path.join(FIXTURES, "test_video.mp4")
FFMPEG_AVAILABLE = shutil.which("ffmpeg") and shutil.which("ffprobe")
pytestmark = pytest.mark.skipif(
    not FFMPEG_AVAILABLE,
    reason="ffmpeg/ffprobe not installed",
)


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


def test_get_video_info():
    info = get_video_info(TEST_VIDEO)
    assert "fps" in info
    assert "total_frames" in info
    assert info["media_type"] == "video"
    assert info["fps"] > 0
    assert info["total_frames"] > 0


def test_extract_frames(tmp_dir):
    frames_dir = os.path.join(tmp_dir, "frames")
    info = extract_frames(TEST_VIDEO, frames_dir)

    assert info["fps"] > 0
    frames = [f for f in os.listdir(frames_dir) if f.endswith(".jpg")]
    assert len(frames) > 0
    # 3 second video at 25fps should produce ~75 frames
    assert len(frames) >= 50


def test_extract_audio(tmp_dir):
    audio_path = os.path.join(tmp_dir, "audio.aac")
    result = extract_audio(TEST_VIDEO, audio_path)
    # Test video may not have audio — extract_audio returns False in that case
    # Both outcomes are valid; we just verify it doesn't crash
    assert isinstance(result, bool)


def test_reassemble_video(tmp_dir):
    # Extract frames first
    frames_dir = os.path.join(tmp_dir, "frames")
    info = extract_frames(TEST_VIDEO, frames_dir)

    audio_path = os.path.join(tmp_dir, "audio.aac")
    extract_audio(TEST_VIDEO, audio_path)

    # Reassemble
    output_path = os.path.join(tmp_dir, "output.mp4")
    reassemble_video(frames_dir, audio_path, output_path, info["fps"])

    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0

    # Verify output is valid video
    out_info = get_video_info(output_path)
    assert out_info["fps"] > 0
    assert out_info["total_frames"] > 0


def test_reassemble_video_pads_odd_dimensions(tmp_dir):
    frames_dir = os.path.join(tmp_dir, "odd_frames")
    os.makedirs(frames_dir, exist_ok=True)

    for index in range(1, 4):
        image = np.zeros((187, 187, 3), dtype=np.uint8)
        image[:] = (index * 30, index * 20, index * 10)
        assert cv2.imwrite(os.path.join(frames_dir, f"frame_{index:04d}.jpg"), image)

    output_path = os.path.join(tmp_dir, "odd_output.mp4")
    reassemble_video(frames_dir, None, output_path, 25.0)

    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0


def test_stage_image_as_frames(tmp_dir):
    image_path = os.path.join(tmp_dir, "source.png")
    image = np.zeros((64, 96, 3), dtype=np.uint8)
    image[:] = (20, 40, 60)
    assert cv2.imwrite(image_path, image)

    frames_dir = os.path.join(tmp_dir, "image_frames")
    info = stage_image_as_frames(image_path, frames_dir)

    assert info["media_type"] == "image"
    assert info["fps"] == 1.0
    assert info["total_frames"] == 1
    assert info["width"] == 96
    assert info["height"] == 64
    assert os.path.exists(os.path.join(frames_dir, "frame_0001.jpg"))


def test_write_image_output(tmp_dir):
    frames_dir = os.path.join(tmp_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    image = np.zeros((48, 80, 3), dtype=np.uint8)
    image[:] = (70, 50, 30)
    assert cv2.imwrite(os.path.join(frames_dir, "frame_0001.jpg"), image)

    output_path = os.path.join(tmp_dir, "output.png")
    write_image_output(frames_dir, output_path)

    assert os.path.exists(output_path)
    rendered = cv2.imread(output_path)
    assert rendered is not None
    assert rendered.shape[:2] == (48, 80)


def test_media_type_for_path():
    assert media_type_for_path("clip.mp4") == "video"
    assert media_type_for_path("portrait.png") == "image"
