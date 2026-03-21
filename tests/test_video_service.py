"""Tests for server/services/video.py — FFmpeg frame extraction and reassembly."""
import os
import sys
import shutil
import tempfile

import pytest

# Add server to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from services.video import extract_frames, extract_audio, reassemble_video, get_video_info

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
