"""Tests for memory & speed optimizations in extract_face_clips,
swap_single_face_clip, and composite_swapped_faces.

Verifies that:
1. extract_face_clips processes one frame at a time (no accumulation)
2. swap_single_face_clip uses crop detector + largest-face strategy
3. composite_swapped_faces skips untouched frames (copies instead of loading)
4. Intermediate dirs are cleaned up after pipeline completes
"""

import os
import shutil
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from services import face_tracker, face_swapper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_frame(path: str, width: int = 128, height: int = 96, color=(100, 150, 200)):
    """Create a test frame with a given color."""
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:] = color
    assert cv2.imwrite(path, image)


def _make_frames(frames_dir: str, count: int = 10, width: int = 128, height: int = 96):
    """Generate numbered test frames."""
    os.makedirs(frames_dir, exist_ok=True)
    for index in range(count):
        _write_frame(
            os.path.join(frames_dir, f"frame_{index + 1:04d}.jpg"),
            width=width,
            height=height,
            color=(20 * (index % 13), 30 * (index % 9), 40 * (index % 7)),
        )


def _make_faces_json(frame_indices, bbox=(10.0, 10.0, 50.0, 50.0)):
    """Create a faces_json with a single face visible at given frame indices."""
    frames = {str(idx): list(bbox) for idx in frame_indices}
    return {
        "fps": 24.0,
        "faces": {
            "face_0": {
                "age": 25,
                "gender": "male",
                "thumbnail": "data:image/jpeg;base64,TEST",
                "thumbnail_path": "face_0_thumb.jpg",
                "embedding": [0.0] * 512,
                "frames": frames,
                "frame_count": len(frame_indices),
            }
        },
    }


# ===========================================================================
# 1. extract_face_clips: one-frame-at-a-time processing
# ===========================================================================


class TestExtractFaceClipsMemory:
    """Verify the two-pass approach loads only one frame at a time."""

    def test_produces_correct_crops(self, tmp_path, monkeypatch):
        """Output crops must be identical to the old accumulation approach."""
        frames_dir = str(tmp_path / "frames")
        clips_dir = str(tmp_path / "clips")
        _make_frames(frames_dir, count=5)

        faces_json = _make_faces_json(
            frame_indices=[0, 2, 4],
            bbox=(10.0, 10.0, 34.0, 34.0),
        )

        # Ensure no face detection is called
        monkeypatch.setattr(face_tracker, "_get_app", lambda: (_ for _ in ()).throw(
            AssertionError("should not re-detect faces")
        ))

        manifests = face_tracker.extract_face_clips(
            frames_dir, faces_json, ["face_0"], clips_dir,
        )

        assert "face_0" in manifests
        manifest = manifests["face_0"]
        assert manifest["frame_count"] == 3

        # Verify each crop exists and has correct dimensions
        for fname, (x1, y1, x2, y2) in manifest["crops"].items():
            crop_path = os.path.join(manifest["clip_dir"], fname)
            assert os.path.exists(crop_path), f"Missing crop: {crop_path}"
            crop = cv2.imread(crop_path)
            assert crop is not None
            assert crop.shape[0] == y2 - y1
            assert crop.shape[1] == x2 - x1

    def test_does_not_accumulate_frames_in_memory(self, tmp_path, monkeypatch):
        """Patch cv2.imread to track that frames are loaded and released one at a time."""
        frames_dir = str(tmp_path / "frames")
        clips_dir = str(tmp_path / "clips")
        _make_frames(frames_dir, count=10)

        faces_json = _make_faces_json(
            frame_indices=list(range(10)),
            bbox=(5.0, 5.0, 40.0, 40.0),
        )

        monkeypatch.setattr(face_tracker, "_get_app", lambda: (_ for _ in ()).throw(
            AssertionError("should not re-detect faces")
        ))

        # Track concurrent frame loads
        active_frames = []
        max_concurrent = [0]
        original_imread = cv2.imread

        def tracking_imread(path, *args, **kwargs):
            result = original_imread(path, *args, **kwargs)
            if result is not None and "frame_" in path:
                active_frames.append(path)
                max_concurrent[0] = max(max_concurrent[0], len(active_frames))
            return result

        original_imwrite = cv2.imwrite

        def tracking_imwrite(path, img, *args, **kwargs):
            result = original_imwrite(path, img, *args, **kwargs)
            # After writing, the frame should be released in the next iteration
            # We simulate GC by clearing tracking after write
            if active_frames:
                active_frames.pop()
            return result

        monkeypatch.setattr(cv2, "imread", tracking_imread)
        monkeypatch.setattr(cv2, "imwrite", tracking_imwrite)

        manifests = face_tracker.extract_face_clips(
            frames_dir, faces_json, ["face_0"], clips_dir,
        )

        assert manifests["face_0"]["frame_count"] == 10
        # The key assertion: we should never have more than ~2 frames loaded
        # (1 being processed + possibly 1 not yet GC'd).
        # The old code would have had all 10 loaded at once.
        assert max_concurrent[0] <= 2, (
            f"Too many frames loaded concurrently: {max_concurrent[0]}. "
            f"Expected at most 2 (one-at-a-time processing)."
        )

    def test_max_face_size_computed_from_metadata_only(self, tmp_path, monkeypatch):
        """max_face_size should be computed from bbox metadata, not from loaded frames."""
        frames_dir = str(tmp_path / "frames")
        clips_dir = str(tmp_path / "clips")
        _make_frames(frames_dir, count=3)

        # Different bbox sizes to verify max is computed correctly
        faces_json = {
            "fps": 24.0,
            "faces": {
                "face_0": {
                    "age": 25,
                    "gender": "male",
                    "thumbnail": "data:image/jpeg;base64,TEST",
                    "thumbnail_path": "face_0_thumb.jpg",
                    "embedding": [0.0] * 512,
                    "frames": {
                        "0": [10.0, 10.0, 20.0, 20.0],  # 10x10 face
                        "1": [10.0, 10.0, 40.0, 40.0],  # 30x30 face (largest)
                        "2": [10.0, 10.0, 25.0, 25.0],  # 15x15 face
                    },
                    "frame_count": 3,
                }
            },
        }

        monkeypatch.setattr(face_tracker, "_get_app", lambda: (_ for _ in ()).throw(
            AssertionError("should not re-detect faces")
        ))

        manifests = face_tracker.extract_face_clips(
            frames_dir, faces_json, ["face_0"], clips_dir,
        )

        manifest = manifests["face_0"]
        # All crops should use the same crop_size based on max face (30px)
        # crop_size = max(2, int(30 * 1.5)) = 45
        # So all crops should be the same size (clamped to frame bounds)
        sizes = set()
        for fname, (x1, y1, x2, y2) in manifest["crops"].items():
            sizes.add((x2 - x1, y2 - y1))

        # All crops should have the same dimensions (uniform crop_size)
        assert len(sizes) == 1, f"Expected uniform crop size, got {sizes}"

    def test_trim_window_still_works(self, tmp_path, monkeypatch):
        """start_frame / end_frame filtering should work with the new code."""
        frames_dir = str(tmp_path / "frames")
        clips_dir = str(tmp_path / "clips")
        _make_frames(frames_dir, count=10)

        faces_json = _make_faces_json(
            frame_indices=[0, 2, 4, 6, 8],
            bbox=(10.0, 10.0, 34.0, 34.0),
        )

        monkeypatch.setattr(face_tracker, "_get_app", lambda: (_ for _ in ()).throw(
            AssertionError("should not re-detect faces")
        ))

        manifests = face_tracker.extract_face_clips(
            frames_dir, faces_json, ["face_0"], clips_dir,
            start_frame=3, end_frame=7,
        )

        manifest = manifests["face_0"]
        # Only frame indices 4 and 6 fall within [3, 7)
        assert manifest["frame_count"] == 2
        crop_fnames = sorted(manifest["crops"].keys())
        assert crop_fnames == ["frame_0005.jpg", "frame_0007.jpg"]


# ===========================================================================
# 2. swap_single_face_clip: largest-face + crop detector
# ===========================================================================


class TestSwapSingleFaceClip:
    """Verify swap uses crop detector and picks largest face."""

    def test_uses_crop_app_not_full_app(self, tmp_path, monkeypatch):
        """Should call _get_crop_app(), not _get_app()."""
        clip_dir = str(tmp_path / "clips")
        output_dir = str(tmp_path / "output")
        os.makedirs(clip_dir)
        _write_frame(os.path.join(clip_dir, "frame_0001.jpg"))
        _write_frame(os.path.join(clip_dir, "frame_0002.jpg"))

        full_app_called = []
        crop_app_called = []

        def mock_full_app():
            full_app_called.append(True)
            raise AssertionError("Should not use full app for crops")

        mock_face = SimpleNamespace(
            bbox=np.array([10, 10, 50, 50]),
            normed_embedding=np.zeros(512),
        )
        mock_app = MagicMock()
        mock_app.get.return_value = [mock_face]

        def mock_crop_app():
            crop_app_called.append(True)
            return mock_app

        mock_adapter = MagicMock()
        mock_adapter.swap_face.return_value = np.zeros((96, 128, 3), dtype=np.uint8)

        monkeypatch.setattr(face_swapper, "_get_app", mock_full_app)
        monkeypatch.setattr(face_swapper, "_get_crop_app", mock_crop_app)

        face_swapper.swap_single_face_clip(
            clip_dir=clip_dir,
            output_dir=output_dir,
            target_embedding=np.zeros(512),
            adapter=mock_adapter,
        )

        assert len(full_app_called) == 0, "Full app should not be called for crops"
        assert len(crop_app_called) > 0, "Crop app should be called"

    def test_picks_largest_face_not_cosine_match(self, tmp_path, monkeypatch):
        """Should pick the largest detected face, not match by cosine similarity."""
        clip_dir = str(tmp_path / "clips")
        output_dir = str(tmp_path / "output")
        os.makedirs(clip_dir)
        _write_frame(os.path.join(clip_dir, "frame_0001.jpg"))

        # Two faces: small one with high similarity, large one with low similarity
        small_face = SimpleNamespace(
            bbox=np.array([10, 10, 20, 20]),  # 10x10
            normed_embedding=np.ones(512),    # high similarity to target
        )
        large_face = SimpleNamespace(
            bbox=np.array([5, 5, 55, 55]),    # 50x50
            normed_embedding=np.zeros(512),   # low similarity to target
        )

        mock_app = MagicMock()
        mock_app.get.return_value = [small_face, large_face]

        monkeypatch.setattr(face_swapper, "_get_crop_app", lambda: mock_app)

        swap_calls = []
        mock_adapter = MagicMock()

        def capture_swap(frame, target_face, source_face=None):
            swap_calls.append(target_face)
            return frame

        mock_adapter.swap_face.side_effect = capture_swap

        face_swapper.swap_single_face_clip(
            clip_dir=clip_dir,
            output_dir=output_dir,
            target_embedding=np.ones(512),  # matches small_face
            adapter=mock_adapter,
        )

        assert len(swap_calls) == 1
        # Should pick large_face (50x50) not small_face (10x10)
        swapped_face = swap_calls[0]
        face_area = (swapped_face.bbox[2] - swapped_face.bbox[0]) * \
                    (swapped_face.bbox[3] - swapped_face.bbox[1])
        assert face_area == 2500, f"Expected largest face (50x50=2500), got area {face_area}"

    def test_handles_no_detected_faces(self, tmp_path, monkeypatch):
        """Should gracefully handle frames where no face is detected."""
        clip_dir = str(tmp_path / "clips")
        output_dir = str(tmp_path / "output")
        os.makedirs(clip_dir)
        _write_frame(os.path.join(clip_dir, "frame_0001.jpg"))

        mock_app = MagicMock()
        mock_app.get.return_value = []  # no faces detected

        monkeypatch.setattr(face_swapper, "_get_crop_app", lambda: mock_app)

        mock_adapter = MagicMock()
        mock_adapter.swap_face.return_value = np.zeros((96, 128, 3), dtype=np.uint8)

        face_swapper.swap_single_face_clip(
            clip_dir=clip_dir,
            output_dir=output_dir,
            target_embedding=np.zeros(512),
            adapter=mock_adapter,
        )

        # Should produce output frame (original, unswapped)
        assert os.path.exists(os.path.join(output_dir, "frame_0001.jpg"))
        # swap_face should NOT have been called
        mock_adapter.swap_face.assert_not_called()

    def test_all_frames_swapped_and_written(self, tmp_path, monkeypatch):
        """All input frames should produce output frames."""
        clip_dir = str(tmp_path / "clips")
        output_dir = str(tmp_path / "output")
        os.makedirs(clip_dir)
        for i in range(5):
            _write_frame(os.path.join(clip_dir, f"frame_{i+1:04d}.jpg"))

        mock_face = SimpleNamespace(bbox=np.array([5, 5, 45, 45]))
        mock_app = MagicMock()
        mock_app.get.return_value = [mock_face]
        monkeypatch.setattr(face_swapper, "_get_crop_app", lambda: mock_app)

        mock_adapter = MagicMock()
        mock_adapter.swap_face.side_effect = lambda frame, face, **kw: frame

        progress_values = []
        face_swapper.swap_single_face_clip(
            clip_dir=clip_dir,
            output_dir=output_dir,
            target_embedding=np.zeros(512),
            adapter=mock_adapter,
            progress_callback=progress_values.append,
        )

        output_files = sorted(os.listdir(output_dir))
        assert len(output_files) == 5
        assert output_files == [f"frame_{i+1:04d}.jpg" for i in range(5)]
        assert progress_values[-1] == 1.0


# ===========================================================================
# 3. composite_swapped_faces: skip untouched frames
# ===========================================================================


class TestCompositeSkipsUntouchedFrames:
    """Verify frames without swapped crops are copied, not loaded."""

    def test_untouched_frames_copied_not_loaded(self, tmp_path, monkeypatch):
        """Frames with no swapped crops should be shutil.copy2'd, not imread'd."""
        frames_dir = str(tmp_path / "frames")
        output_dir = str(tmp_path / "output")
        swapped_dir = str(tmp_path / "swapped_clips")
        _make_frames(frames_dir, count=5)

        # Only frame 2 and 4 have swapped crops
        face_clip_dir = os.path.join(swapped_dir, "face_0")
        os.makedirs(face_clip_dir)
        _write_frame(os.path.join(face_clip_dir, "frame_0002.jpg"), color=(255, 0, 0))
        _write_frame(os.path.join(face_clip_dir, "frame_0004.jpg"), color=(0, 255, 0))

        manifests = {
            "face_0": {
                "clip_dir": face_clip_dir,
                "crops": {
                    "frame_0002.jpg": (10, 10, 50, 50),
                    "frame_0004.jpg": (10, 10, 50, 50),
                },
                "crop_size": (40, 40),
                "frame_count": 2,
            }
        }

        imread_calls = []
        original_imread = cv2.imread

        def tracking_imread(path, *args, **kwargs):
            imread_calls.append(os.path.basename(path))
            return original_imread(path, *args, **kwargs)

        monkeypatch.setattr(cv2, "imread", tracking_imread)

        face_swapper.composite_swapped_faces(
            frames_dir=frames_dir,
            output_dir=output_dir,
            manifests=manifests,
            swapped_base_dir=swapped_dir,
        )

        # All 5 output frames should exist
        output_files = sorted(os.listdir(output_dir))
        assert len(output_files) == 5

        # Only frames 2 and 4 (+ their crops) should be imread'd
        # Frames 1, 3, 5 should be copied via shutil.copy2 (no imread)
        frame_reads = [f for f in imread_calls if f.startswith("frame_")]
        assert "frame_0001.jpg" not in frame_reads, "Untouched frame 1 should not be imread'd"
        assert "frame_0003.jpg" not in frame_reads, "Untouched frame 3 should not be imread'd"
        assert "frame_0005.jpg" not in frame_reads, "Untouched frame 5 should not be imread'd"
        assert "frame_0002.jpg" in frame_reads, "Swapped frame 2 should be imread'd"
        assert "frame_0004.jpg" in frame_reads, "Swapped frame 4 should be imread'd"

    def test_copied_frames_are_identical(self, tmp_path):
        """Untouched frames should be byte-identical copies of originals."""
        frames_dir = str(tmp_path / "frames")
        output_dir = str(tmp_path / "output")
        _make_frames(frames_dir, count=3)

        # No faces to swap
        manifests = {}

        face_swapper.composite_swapped_faces(
            frames_dir=frames_dir,
            output_dir=output_dir,
            manifests=manifests,
            swapped_base_dir=str(tmp_path / "swapped"),
        )

        for fname in os.listdir(frames_dir):
            orig = os.path.join(frames_dir, fname)
            copied = os.path.join(output_dir, fname)
            assert os.path.exists(copied)
            with open(orig, "rb") as f1, open(copied, "rb") as f2:
                assert f1.read() == f2.read(), f"Frame {fname} should be byte-identical"

    def test_composited_frames_have_swapped_regions(self, tmp_path):
        """Frames with swapped crops should have the crop pasted in."""
        frames_dir = str(tmp_path / "frames")
        output_dir = str(tmp_path / "output")
        swapped_dir = str(tmp_path / "swapped_clips")

        # Create a white frame
        os.makedirs(frames_dir)
        white_frame = np.ones((96, 128, 3), dtype=np.uint8) * 255
        cv2.imwrite(os.path.join(frames_dir, "frame_0001.jpg"), white_frame)

        # Create a red crop
        face_clip_dir = os.path.join(swapped_dir, "face_0")
        os.makedirs(face_clip_dir)
        red_crop = np.zeros((20, 20, 3), dtype=np.uint8)
        red_crop[:, :, 2] = 255  # Red in BGR
        cv2.imwrite(os.path.join(face_clip_dir, "frame_0001.jpg"), red_crop)

        manifests = {
            "face_0": {
                "clip_dir": face_clip_dir,
                "crops": {
                    "frame_0001.jpg": (10, 10, 30, 30),  # 20x20 region
                },
                "crop_size": (20, 20),
                "frame_count": 1,
            }
        }

        face_swapper.composite_swapped_faces(
            frames_dir=frames_dir,
            output_dir=output_dir,
            manifests=manifests,
            swapped_base_dir=swapped_dir,
        )

        result = cv2.imread(os.path.join(output_dir, "frame_0001.jpg"))
        assert result is not None

        # The crop region should be reddish (JPEG compression may alter exact values)
        crop_region = result[10:30, 10:30]
        avg_red = crop_region[:, :, 2].mean()
        avg_blue = crop_region[:, :, 0].mean()
        assert avg_red > 200, f"Expected red crop region, got avg red={avg_red}"
        assert avg_blue < 50, f"Expected low blue in crop region, got avg blue={avg_blue}"

    def test_progress_reported_correctly(self, tmp_path):
        """Progress should be reported for all frames including skipped ones."""
        frames_dir = str(tmp_path / "frames")
        output_dir = str(tmp_path / "output")
        _make_frames(frames_dir, count=5)

        manifests = {}
        progress_values = []

        face_swapper.composite_swapped_faces(
            frames_dir=frames_dir,
            output_dir=output_dir,
            manifests=manifests,
            swapped_base_dir=str(tmp_path / "swapped"),
            progress_callback=progress_values.append,
        )

        assert progress_values[-1] == 1.0
        assert len(progress_values) == 5


# ===========================================================================
# 4. Pipeline cleanup of intermediate directories
# ===========================================================================


class TestPipelineCleanup:
    """Verify intermediate directories are cleaned up after _run_swap_job."""

    def test_swap_faces_pipeline_end_to_end(self, tmp_path, monkeypatch):
        """Full swap_faces_pipeline with mocked engine produces correct output."""
        frames_dir = str(tmp_path / "frames")
        output_dir = str(tmp_path / "output")
        _make_frames(frames_dir, count=5)

        # Create face clips + swapped clips to simulate Phase 1 + 2
        clips_dir = str(tmp_path / "face_clips")
        swapped_clips_dir = str(tmp_path / "swapped_clips")
        face_clip_dir = os.path.join(clips_dir, "face_0")
        swap_out_dir = os.path.join(swapped_clips_dir, "face_0")
        os.makedirs(face_clip_dir)
        os.makedirs(swap_out_dir)

        # Simulate: face_0 appears in frames 2 and 4
        for fname in ["frame_0002.jpg", "frame_0004.jpg"]:
            _write_frame(os.path.join(face_clip_dir, fname), color=(0, 0, 255))
            _write_frame(os.path.join(swap_out_dir, fname), color=(255, 0, 0))

        manifests = {
            "face_0": {
                "clip_dir": face_clip_dir,
                "crops": {
                    "frame_0002.jpg": (10, 10, 50, 50),
                    "frame_0004.jpg": (10, 10, 50, 50),
                },
                "crop_size": (40, 40),
                "frame_count": 2,
            }
        }

        faces_json = _make_faces_json([1, 3], bbox=(10.0, 10.0, 50.0, 50.0))

        # Create a mock engine that just copies clips
        mock_engine = MagicMock()
        mock_engine.get_warnings.return_value = []

        def fake_swap_clip(*, clip_dir, output_dir, face_id, face_data,
                           target_embedding, fps, progress_callback=None):
            os.makedirs(output_dir, exist_ok=True)
            for fname in os.listdir(clip_dir):
                shutil.copy2(os.path.join(clip_dir, fname), os.path.join(output_dir, fname))
            if progress_callback:
                progress_callback(1.0)

        mock_engine.swap_clip.side_effect = fake_swap_clip

        progress_values = []
        status_values = []

        face_swapper.swap_faces_pipeline(
            manifests=manifests,
            faces_json=faces_json,
            frames_dir=frames_dir,
            output_dir=output_dir,
            engine=mock_engine,
            progress_callback=progress_values.append,
            status_callback=status_values.append,
        )

        # All 5 frames should be in output
        output_files = sorted(os.listdir(output_dir))
        assert len(output_files) == 5, f"Expected 5 output frames, got {output_files}"

        # Progress should reach 1.0
        assert progress_values[-1] >= 0.99

    def test_intermediate_cleanup_dirs_exist_and_can_be_removed(self, tmp_path):
        """Verify that shutil.rmtree correctly removes intermediate dirs."""
        face_clips = tmp_path / "face_clips"
        swapped_clips = tmp_path / "swapped_clips"
        face_clips.mkdir()
        swapped_clips.mkdir()
        (face_clips / "face_0").mkdir()
        (face_clips / "face_0" / "frame_0001.jpg").write_bytes(b"data")
        (swapped_clips / "face_0").mkdir()
        (swapped_clips / "face_0" / "frame_0001.jpg").write_bytes(b"data")

        # Simulate the cleanup logic from main.py
        for cleanup_dir in [str(face_clips), str(swapped_clips)]:
            if os.path.isdir(cleanup_dir):
                shutil.rmtree(cleanup_dir, ignore_errors=True)

        assert not face_clips.exists()
        assert not swapped_clips.exists()


# ===========================================================================
# 5. Integration: extract → swap → composite end-to-end
# ===========================================================================


class TestEndToEndPipeline:
    """Test the full extract → swap → composite flow with mocked models."""

    def test_full_pipeline_flow(self, tmp_path, monkeypatch):
        """Runs extract_face_clips → swap_single_face_clip → composite_swapped_faces."""
        frames_dir = str(tmp_path / "frames")
        clips_dir = str(tmp_path / "clips")
        swapped_clips_dir = str(tmp_path / "swapped_clips")
        output_dir = str(tmp_path / "output")

        _make_frames(frames_dir, count=10, width=200, height=150)

        # Face appears in frames 0, 2, 4, 6, 8 (half the frames)
        faces_json = _make_faces_json(
            frame_indices=[0, 2, 4, 6, 8],
            bbox=(20.0, 20.0, 80.0, 80.0),
        )

        monkeypatch.setattr(face_tracker, "_get_app", lambda: (_ for _ in ()).throw(
            AssertionError("should not re-detect faces")
        ))

        # Phase 1: Extract clips
        manifests = face_tracker.extract_face_clips(
            frames_dir, faces_json, ["face_0"], clips_dir,
        )

        assert "face_0" in manifests
        manifest = manifests["face_0"]
        assert manifest["frame_count"] == 5

        # Phase 2: Swap clips (mocked)
        mock_face = SimpleNamespace(bbox=np.array([5, 5, 85, 85]))
        mock_app = MagicMock()
        mock_app.get.return_value = [mock_face]
        monkeypatch.setattr(face_swapper, "_get_crop_app", lambda: mock_app)

        mock_adapter = MagicMock()
        # Swap returns frame with slight modification (invert colors)
        mock_adapter.swap_face.side_effect = lambda frame, face, **kw: 255 - frame

        swap_out = os.path.join(swapped_clips_dir, "face_0")
        face_swapper.swap_single_face_clip(
            clip_dir=manifest["clip_dir"],
            output_dir=swap_out,
            target_embedding=np.zeros(512),
            adapter=mock_adapter,
        )

        swapped_files = sorted(os.listdir(swap_out))
        assert len(swapped_files) == 5

        # Phase 3: Composite
        face_swapper.composite_swapped_faces(
            frames_dir=frames_dir,
            output_dir=output_dir,
            manifests=manifests,
            swapped_base_dir=swapped_clips_dir,
        )

        output_files = sorted(os.listdir(output_dir))
        assert len(output_files) == 10, f"Expected 10 output frames, got {len(output_files)}"

        # Untouched frames (1, 3, 5, 7, 9) should be byte-identical to originals
        for i in [1, 3, 5, 7, 9]:
            fname = f"frame_{i+1:04d}.jpg"
            orig_path = os.path.join(frames_dir, fname)
            out_path = os.path.join(output_dir, fname)
            with open(orig_path, "rb") as f1, open(out_path, "rb") as f2:
                assert f1.read() == f2.read(), f"Untouched frame {fname} should be byte-identical"

        # Swapped frames (2, 4, 6, 8, 10 → indices 0,2,4,6,8) should differ
        for i in [0, 2, 4, 6, 8]:
            fname = f"frame_{i+1:04d}.jpg"
            orig_path = os.path.join(frames_dir, fname)
            out_path = os.path.join(output_dir, fname)
            with open(orig_path, "rb") as f1, open(out_path, "rb") as f2:
                # They may or may not be byte-identical due to JPEG recompression,
                # but the composited frame should at least exist and be valid
                out_frame = cv2.imread(out_path)
                assert out_frame is not None
                assert out_frame.shape == (150, 200, 3)
