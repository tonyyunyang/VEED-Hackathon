"""Tests for server/services/face_swapper.py."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from services import face_swapper


def test_reference_face_resolver_prefers_age_matched_gender_file(tmp_path):
    refs_dir = tmp_path / "reference_faces"
    male_dir = refs_dir / "male"
    male_dir.mkdir(parents=True)

    young = male_dir / "20-29_alpha.jpg"
    older = male_dir / "40-49_beta.jpg"
    young.write_bytes(b"young")
    older.write_bytes(b"older")

    resolver = face_swapper.ReferenceFaceResolver(
        reference_image="",
        reference_faces_dir=str(refs_dir),
        allow_target_thumbnail_fallback=False,
    )

    resolved = resolver.resolve(
        str(tmp_path),
        "face_0",
        {"gender": "male", "age": 25},
    )

    assert resolved == str(young)


def test_reference_face_resolver_falls_back_to_thumbnail(tmp_path):
    video_dir = tmp_path / "video"
    video_dir.mkdir()
    thumbnail_path = video_dir / "face_0_thumb.jpg"
    thumbnail_path.write_bytes(b"thumb")

    resolver = face_swapper.ReferenceFaceResolver(
        reference_image="",
        reference_faces_dir=str(tmp_path / "missing"),
        allow_target_thumbnail_fallback=True,
    )

    resolved = resolver.resolve(
        str(video_dir),
        "face_0",
        {"thumbnail_path": "face_0_thumb.jpg", "gender": "female", "age": 31},
    )

    assert resolved == str(thumbnail_path)


def test_copy_and_restore_sparse_clip_frames(tmp_path):
    clip_dir = tmp_path / "clip"
    sequence_dir = tmp_path / "sequence"
    generated_dir = tmp_path / "generated"
    output_dir = tmp_path / "output"

    clip_dir.mkdir()
    generated_dir.mkdir()

    (clip_dir / "frame_0001.jpg").write_bytes(b"original-1")
    (clip_dir / "frame_0004.jpg").write_bytes(b"original-4")

    original_names = face_swapper._copy_clip_frames_to_sequence(
        str(clip_dir),
        str(sequence_dir),
    )

    assert original_names == ["frame_0001.jpg", "frame_0004.jpg"]
    assert (sequence_dir / "frame_0001.jpg").read_bytes() == b"original-1"
    assert (sequence_dir / "frame_0002.jpg").read_bytes() == b"original-4"

    (generated_dir / "frame_0001.jpg").write_bytes(b"swapped-1")
    face_swapper._restore_output_frames(
        original_names=original_names,
        sequence_output_dir=str(generated_dir),
        original_clip_dir=str(clip_dir),
        output_dir=str(output_dir),
    )

    assert (output_dir / "frame_0001.jpg").read_bytes() == b"swapped-1"
    assert (output_dir / "frame_0004.jpg").read_bytes() == b"original-4"


def test_create_swap_engine_respects_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(face_swapper, "FACE_SWAPPER_BACKEND", "insightface")
    engine = face_swapper.create_swap_engine(str(tmp_path))
    assert isinstance(engine, face_swapper.InsightFaceSwapEngine)

    monkeypatch.setattr(face_swapper, "FACE_SWAPPER_BACKEND", "facefusion")
    engine = face_swapper.create_swap_engine(str(tmp_path))
    assert isinstance(engine, face_swapper.FaceFusionSwapEngine)


def test_create_swap_engine_rejects_unknown_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(face_swapper, "FACE_SWAPPER_BACKEND", "unknown")

    try:
        face_swapper.create_swap_engine(str(tmp_path))
    except ValueError as exc:
        assert "Unsupported FACE_SWAPPER_BACKEND" in str(exc)
    else:
        raise AssertionError("Expected create_swap_engine to reject an unknown backend")


def test_facefusion_build_swap_cmd(monkeypatch, tmp_path):
    monkeypatch.setattr(face_swapper, "FACEFUSION_PYTHON", "/opt/veed/bin/python")
    monkeypatch.setattr(face_swapper, "FACEFUSION_ENABLE_ENHANCER", True)
    monkeypatch.setattr(face_swapper, "FACEFUSION_EXECUTION_PROVIDER", "cpu")
    monkeypatch.setattr(face_swapper, "FACEFUSION_SWAP_MODEL", "hyperswap_1a_256")
    monkeypatch.setattr(face_swapper, "FACEFUSION_PIXEL_BOOST", "512x512")
    monkeypatch.setattr(face_swapper, "FACEFUSION_OUTPUT_VIDEO_QUALITY", 90)
    monkeypatch.setattr(face_swapper, "FACEFUSION_THREAD_COUNT", 3)

    engine = face_swapper.FaceFusionSwapEngine(str(tmp_path))
    cmd = engine._build_swap_cmd(
        source_path="/tmp/source.jpg",
        target_path="/tmp/input.mp4",
        output_path="/tmp/output.mp4",
        temp_path="/tmp/facefusion-temp",
        jobs_path="/tmp/facefusion-jobs",
    )

    assert cmd[0] == "/opt/veed/bin/python"
    assert "headless-run" in cmd
    assert "--temp-path" in cmd and "/tmp/facefusion-temp" in cmd
    assert "--jobs-path" in cmd and "/tmp/facefusion-jobs" in cmd
    assert "--processors" in cmd
    assert "face_swapper" in cmd
    assert "face_enhancer" in cmd
    assert "--face-selector-mode" in cmd and "one" in cmd


def test_swap_faces_pipeline_respects_selected_frame_names(tmp_path):
    frames_dir = tmp_path / "frames"
    output_dir = tmp_path / "output"
    frames_dir.mkdir()

    for index in range(1, 5):
        (frames_dir / f"frame_{index:04d}.jpg").write_bytes(f"frame-{index}".encode())

    progress_updates: list[float] = []
    status_updates: list[dict] = []

    face_swapper.swap_faces_pipeline(
        manifests={},
        faces_json={"fps": 24.0, "faces": {}},
        frames_dir=str(frames_dir),
        output_dir=str(output_dir),
        progress_callback=progress_updates.append,
        status_callback=status_updates.append,
        frame_names=["frame_0002.jpg", "frame_0004.jpg"],
    )

    assert sorted(os.listdir(output_dir)) == ["frame_0002.jpg", "frame_0004.jpg"]
    assert progress_updates[-1] == 1.0
    assert status_updates[-1]["phase"] == "compositing"
    assert status_updates[-1]["completed_frames"] == 2
    assert status_updates[-1]["total_frames"] == 2
