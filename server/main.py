import logging
import os
import time as _time
import uuid
import json
import hashlib
import asyncio
import shutil
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from models.schemas import (
    DetectFacesRequest, DetectFacesResponse, FaceInfo,
    StatusResponse, SwapRequest, SwapResponse, UploadResponse,
)
from config import (
    DUMMY_TRACKING,
    ROOT_DIR,
    STORAGE_DIR,
    ENABLE_LIPSYNC,
    FACE_SWAPPER_BACKEND,
    FACE_SWAP_REFERENCE_IMAGE,
    FACEFUSION_ENABLE_ENHANCER,
    FACEFUSION_OUTPUT_VIDEO_QUALITY,
    FACEFUSION_PIXEL_BOOST,
    FACEFUSION_SWAP_MODEL,
    FRAME_SUBSAMPLE,
    TRACKER_BACKEND,
    TRACKER_DET_SIZE,
    TRACKER_DET_THRESH,
    TRACKER_DEVICE,
    TRACKER_FILTER_CONFIDENCE,
    TRACKER_FILTER_TRACKS,
    TRACKER_MIN_CONFIDENCE,
    TRACKER_MIN_TRACK_LENGTH,
    TRACKER_MIN_TRACK_MEDIAN_AREA,
    TRACKER_NMS_THRESH,
    TRACKER_NUM_BINS,
    TRACKER_SHOT_CHANGE_THRESHOLD,
    TRACKER_SIMILARITY_THRESHOLD,
    TRACKER_TIMEOUT_SECONDS,
    TRACKER_TYPE,
    TRACKER_USE_SHARED_MEMORY,
    TRACKER_USE_SHOT_CHANGE,
    FACE_ANALYSIS_DEVICE,
)
from services import video, face_tracker, face_swapper

logger = logging.getLogger(__name__)


def _configure_face_tracker_backend() -> None:
    """Expose tracker config to the compatibility layer as module hints."""

    face_tracker.TRACKER_BACKEND = TRACKER_BACKEND
    face_tracker.TRACKER_TYPE = TRACKER_TYPE
    face_tracker.TRACKER_DEVICE = TRACKER_DEVICE
    face_tracker.DEFAULT_TRACKER_TYPE = TRACKER_TYPE
    face_tracker.DEFAULT_TRACKER_DEVICE = TRACKER_DEVICE
    face_tracker.TRACKER_DET_SIZE = TRACKER_DET_SIZE
    face_tracker.TRACKER_DET_THRESH = TRACKER_DET_THRESH
    face_tracker.TRACKER_NMS_THRESH = TRACKER_NMS_THRESH
    face_tracker.TRACKER_NUM_BINS = TRACKER_NUM_BINS
    face_tracker.TRACKER_SHOT_CHANGE_THRESHOLD = TRACKER_SHOT_CHANGE_THRESHOLD
    face_tracker.DEFAULT_TRACKER_SIMILARITY_THRESHOLD = TRACKER_SIMILARITY_THRESHOLD
    face_tracker.TRACKER_FILTER_TRACKS = TRACKER_FILTER_TRACKS
    face_tracker.TRACKER_MIN_TRACK_LENGTH = TRACKER_MIN_TRACK_LENGTH
    face_tracker.TRACKER_MIN_TRACK_MEDIAN_AREA = TRACKER_MIN_TRACK_MEDIAN_AREA
    face_tracker.TRACKER_FILTER_CONFIDENCE = TRACKER_FILTER_CONFIDENCE
    face_tracker.TRACKER_MIN_CONFIDENCE = TRACKER_MIN_CONFIDENCE
    face_tracker.TRACKER_USE_SHOT_CHANGE = TRACKER_USE_SHOT_CHANGE
    face_tracker.TRACKER_USE_SHARED_MEMORY = TRACKER_USE_SHARED_MEMORY
    face_tracker.TRACKER_TIMEOUT_SECONDS = TRACKER_TIMEOUT_SECONDS
    face_tracker.FACE_ANALYSIS_DEVICE = FACE_ANALYSIS_DEVICE
    face_tracker.FRAME_SUBSAMPLE = FRAME_SUBSAMPLE
    face_tracker.DUMMY_TRACKING = DUMMY_TRACKING


_configure_face_tracker_backend()

app = FastAPI(title="VEED Face Swap")
app.state.tracker_backend = TRACKER_BACKEND

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

jobs: dict[str, dict] = {}
swap_lock = asyncio.Lock()
_STALE_JOB_SECONDS = 180  # mark job failed if no update for 3 minutes
DEMO_VIDEO_PROJECTS_DIR = Path(ROOT_DIR) / "src" / "assets" / "video-projects"
DEMO_CACHE_METADATA_FILENAME = "demo_cache.json"
SWAP_CACHE_DIRNAME = "swap_cache"
SWAP_CACHE_METADATA_FILENAME = "swap_cache.json"


def _media_dir(media_id: str) -> str:
    path = os.path.join(STORAGE_DIR, media_id)
    if not os.path.realpath(path).startswith(os.path.realpath(STORAGE_DIR)):
        raise HTTPException(status_code=400, detail="Invalid media ID")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Media not found")
    return path


def _video_dir(video_id: str) -> str:
    return _media_dir(video_id)


def _find_original_media(media_dir: str) -> str | None:
    for file_name in os.listdir(media_dir):
        if file_name.startswith("original"):
            return os.path.join(media_dir, file_name)
    return None


def _demo_media_id(demo_id: str) -> str:
    normalized = demo_id.strip().lower()
    if not normalized:
        raise ValueError("Demo ID is required")
    return f"demo_{normalized.replace('-', '_')}"


def _demo_video_path(demo_id: str) -> Path:
    demo_path = DEMO_VIDEO_PROJECTS_DIR / f"{demo_id}.mp4"
    if not demo_path.is_file():
        raise FileNotFoundError(f"Demo video not found for {demo_id}: {demo_path}")
    return demo_path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _demo_cache_metadata(video_dir: str) -> dict | None:
    metadata_path = Path(video_dir) / DEMO_CACHE_METADATA_FILENAME
    if not metadata_path.is_file():
        return None
    try:
        with metadata_path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def _write_demo_cache_metadata(video_dir: str, payload: dict) -> None:
    metadata_path = Path(video_dir) / DEMO_CACHE_METADATA_FILENAME
    with metadata_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _has_cached_analysis_artifacts(video_dir: str, media_type: str) -> bool:
    faces_path = os.path.join(video_dir, "faces.json")
    frames_dir = os.path.join(video_dir, "frames")
    if not os.path.exists(faces_path):
        return False
    if not os.path.isdir(frames_dir) or not _frame_files(frames_dir):
        return False
    return True


def _load_detect_faces_response(media_id: str, faces_json: dict) -> DetectFacesResponse:
    media_type = str(faces_json.get("media_type") or "video").lower()
    faces_list = [
        FaceInfo(
            face_id=fid,
            thumbnail=fdata["thumbnail"],
            age=fdata["age"],
            gender=fdata["gender"],
            frame_count=fdata["frame_count"],
            frames=fdata.get("frames", {}),
        )
        for fid, fdata in faces_json["faces"].items()
    ]
    return DetectFacesResponse(
        video_id=media_id,
        media_id=media_id,
        media_type=media_type,
        fps=float(faces_json["fps"]),
        total_frames=int(faces_json["total_frames"]),
        width=faces_json.get("width"),
        height=faces_json.get("height"),
        faces=faces_list,
    )


def _analyze_media_sync(media_id: str, force: bool = False) -> DetectFacesResponse:
    vdir = _media_dir(media_id)

    original = _find_original_media(vdir)
    if not original:
        raise HTTPException(status_code=404, detail="Original media not found")

    frames_dir = os.path.join(vdir, "frames")
    media_type = video.media_type_for_path(original)

    if not force and _has_cached_analysis_artifacts(vdir, media_type):
        faces_json = face_tracker.load_faces_json(os.path.join(vdir, "faces.json"))
        return _load_detect_faces_response(media_id, faces_json)

    shutil.rmtree(frames_dir, ignore_errors=True)
    Path(os.path.join(vdir, "audio.aac")).unlink(missing_ok=True)

    if media_type == "image":
        media_info = video.stage_image_as_frames(original, frames_dir)
        faces_data = face_tracker.detect_faces_in_image(original, vdir)
    else:
        media_info = video.extract_frames(original, frames_dir)
        audio_path = os.path.join(vdir, "audio.aac")
        video.extract_audio(original, audio_path)
        faces_data = face_tracker.detect_and_cluster(frames_dir, vdir, FRAME_SUBSAMPLE)

    face_tracker.save_faces_json(faces_data, media_info, os.path.join(vdir, "faces.json"))
    return _load_detect_faces_response(
        media_id,
        {"faces": faces_data["faces"], **media_info},
    )


def ensure_demo_detection_cache(demo_id: str, *, force: bool = False) -> DetectFacesResponse:
    source_path = _demo_video_path(demo_id)
    media_id = _demo_media_id(demo_id)
    video_dir = os.path.join(STORAGE_DIR, media_id)
    original_path = os.path.join(video_dir, f"original{source_path.suffix.lower()}")
    source_sha256 = _sha256_file(source_path)
    existing_metadata = _demo_cache_metadata(video_dir)

    cache_matches_source = (
        existing_metadata is not None
        and existing_metadata.get("demo_id") == demo_id
        and existing_metadata.get("source_sha256") == source_sha256
        and os.path.exists(original_path)
    )

    if force or not cache_matches_source:
        shutil.rmtree(video_dir, ignore_errors=True)
        os.makedirs(video_dir, exist_ok=True)
        shutil.copy2(source_path, original_path)
        _write_demo_cache_metadata(
            video_dir,
            {
                "demo_id": demo_id,
                "media_id": media_id,
                "source_path": str(source_path),
                "source_sha256": source_sha256,
            },
        )

    return _analyze_media_sync(media_id)


def _output_metadata_for_media(media_dir: str, faces_json: dict) -> tuple[str, str, str]:
    media_type = str(faces_json.get("media_type") or "video").lower()
    if media_type == "image":
        original_media = _find_original_media(media_dir)
        output_extension = str(
            faces_json.get("output_extension")
            or video.output_image_extension_for_path(original_media or "output.png")
        )
        output_path = os.path.join(media_dir, f"output{output_extension}")
        if output_extension in {".jpg", ".jpeg"}:
            mime_type = "image/jpeg"
        elif output_extension == ".webp":
            mime_type = "image/webp"
        else:
            mime_type = "image/png"
        return output_path, mime_type, f"swapped{output_extension}"

    return os.path.join(media_dir, "output.mp4"), "video/mp4", "swapped.mp4"


def _frame_files(frames_dir: str) -> list[str]:
    return sorted(
        file_name
        for file_name in os.listdir(frames_dir)
        if file_name.startswith("frame_") and file_name.endswith(".jpg")
    )


def _resolve_frame_window(
    frames_dir: str,
    start_frame: int | None,
    end_frame: int | None,
) -> tuple[list[str], int, int]:
    frame_files = _frame_files(frames_dir)
    total_frames = len(frame_files)
    if total_frames == 0:
        return [], 0, 0

    resolved_start = min(max(int(start_frame or 0), 0), total_frames - 1)
    resolved_end = total_frames if end_frame is None else min(max(int(end_frame), resolved_start + 1), total_frames)
    return frame_files[resolved_start:resolved_end], resolved_start, resolved_end


def _stage_frame_sequence(source_dir: str, frame_names: list[str], output_dir: str) -> None:
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    for index, file_name in enumerate(frame_names, start=1):
        shutil.copy2(
            os.path.join(source_dir, file_name),
            os.path.join(output_dir, f"frame_{index:04d}.jpg"),
        )


def _update_job(job_id: str, **fields) -> None:
    if job_id not in jobs:
        return
    fields["_last_updated"] = _time.monotonic()
    jobs[job_id].update(fields)


def _find_uploaded_reference(media_dir: str) -> str | None:
    for file_name in sorted(os.listdir(media_dir)):
        if file_name.startswith("uploaded_reference"):
            path = os.path.join(media_dir, file_name)
            if os.path.isfile(path):
                return path
    return None


def _optional_file_sha256(path: str | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_file():
        return None
    return _sha256_file(candidate)


def _swap_cache_manifest_path(media_dir: str) -> Path:
    return Path(media_dir) / SWAP_CACHE_METADATA_FILENAME


def _load_swap_cache_manifest(media_dir: str) -> dict:
    manifest_path = _swap_cache_manifest_path(media_dir)
    if not manifest_path.is_file():
        return {"entries": {}}
    try:
        with manifest_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"entries": {}}
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        return {"entries": {}}
    return {"entries": entries}


def _write_swap_cache_manifest(media_dir: str, manifest: dict) -> None:
    manifest_path = _swap_cache_manifest_path(media_dir)
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)


def _swap_cache_request_payload(
    media_dir: str,
    faces_json: dict,
    face_ids: list[str],
    start_frame: int,
    end_frame: int,
    style_prompt: str,
) -> dict:
    original_media = _find_original_media(media_dir)
    uploaded_reference = _find_uploaded_reference(media_dir)
    payload: dict[str, object] = {
        "face_ids": sorted(face_ids),
        "start_frame": int(start_frame),
        "end_frame": int(end_frame),
        "style_prompt": style_prompt.strip(),
        "media_type": str(faces_json.get("media_type") or "video").lower(),
        "swap_backend": FACE_SWAPPER_BACKEND,
        "source_sha256": _optional_file_sha256(original_media),
        "uploaded_reference_sha256": _optional_file_sha256(uploaded_reference),
        "configured_reference_image_sha256": _optional_file_sha256(
            FACE_SWAP_REFERENCE_IMAGE or None,
        ),
    }
    if FACE_SWAPPER_BACKEND == "facefusion":
        payload["facefusion"] = {
            "swap_model": FACEFUSION_SWAP_MODEL,
            "pixel_boost": FACEFUSION_PIXEL_BOOST,
            "enhancer_enabled": FACEFUSION_ENABLE_ENHANCER,
            "output_video_quality": FACEFUSION_OUTPUT_VIDEO_QUALITY,
        }
    return payload


def _swap_cache_key(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]


def _swap_cache_output_path(media_dir: str, cache_key: str, output_filename: str) -> Path:
    extension = Path(output_filename).suffix or ".mp4"
    cache_dir = Path(media_dir) / SWAP_CACHE_DIRNAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{cache_key}{extension}"


def _lookup_cached_swap(media_dir: str, cache_key: str) -> dict | None:
    manifest = _load_swap_cache_manifest(media_dir)
    entry = manifest["entries"].get(cache_key)
    if not isinstance(entry, dict):
        return None
    output_path = entry.get("output_path")
    if not isinstance(output_path, str) or not os.path.exists(output_path):
        return None
    return entry


def _store_cached_swap(
    media_dir: str,
    cache_key: str,
    request_payload: dict,
    output_path: str,
    output_filename: str,
    media_type: str,
    output_media_type: str,
    warnings: list[str] | None,
) -> str:
    cached_output_path = _swap_cache_output_path(media_dir, cache_key, output_filename)
    source_path = Path(output_path)
    if source_path.resolve() != cached_output_path.resolve():
        shutil.copy2(source_path, cached_output_path)

    manifest = _load_swap_cache_manifest(media_dir)
    manifest["entries"][cache_key] = {
        "request": request_payload,
        "output_path": str(cached_output_path),
        "output_filename": output_filename,
        "media_type": media_type,
        "output_media_type": output_media_type,
        "warnings": warnings or [],
    }
    _write_swap_cache_manifest(media_dir, manifest)
    return str(cached_output_path)


@app.post("/api/upload", response_model=UploadResponse)
async def upload_video(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    allowed = video.VIDEO_EXTENSIONS | video.IMAGE_EXTENSIONS
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid media format: {ext}")

    try:
        media_type = video.media_type_for_path(file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    media_id = str(uuid.uuid4())[:8]
    media_dir = os.path.join(STORAGE_DIR, media_id)
    os.makedirs(media_dir, exist_ok=True)

    media_path = os.path.join(media_dir, f"original{ext}")
    with open(media_path, "wb") as f:
        content = await file.read()
        f.write(content)

    return UploadResponse(video_id=media_id, media_id=media_id, media_type=media_type)


@app.post("/api/upload-reference/{video_id}")
async def upload_reference(video_id: str, file: UploadFile = File(...)):
    """Upload a reference face image for a video.

    This image will be used as the source identity for face swaps,
    taking priority over AI generation and the reference library.
    """
    vdir = _video_dir(video_id)

    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid image format: {ext}")

    ref_path = os.path.join(vdir, f"uploaded_reference{ext}")
    # Remove any previous uploaded reference
    for existing in os.listdir(vdir):
        if existing.startswith("uploaded_reference"):
            Path(os.path.join(vdir, existing)).unlink(missing_ok=True)

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Reference image too large (max 10MB)")

    with open(ref_path, "wb") as f:
        f.write(content)

    return {"video_id": video_id, "reference_path": f"uploaded_reference{ext}"}


@app.post("/api/detect-faces", response_model=DetectFacesResponse)
async def detect_faces(req: DetectFacesRequest):
    media_id = req.media_id or req.video_id
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _analyze_media_sync, media_id, req.force)


async def _run_swap_job(
    job_id: str,
    media_id: str,
    face_ids: list[str],
    start_frame: int | None = None,
    end_frame: int | None = None,
    style_prompt: str = "",
    swap_cache_key: str | None = None,
    swap_cache_request: dict | None = None,
):
    async with swap_lock:  # TODO do I need a lock for the //?
        try:
            vdir = os.path.join(STORAGE_DIR, media_id)
            frames_dir = os.path.join(vdir, "frames")
            swapped_dir = os.path.join(vdir, "swapped")
            faces_json = face_tracker.load_faces_json(os.path.join(vdir, "faces.json"))
            media_type = str(faces_json.get("media_type") or "video").lower()
            frame_names, resolved_start, resolved_end = _resolve_frame_window(
                frames_dir,
                start_frame,
                end_frame,
            )
            total_selected_frames = len(frame_names)
            if total_selected_frames == 0:
                raise RuntimeError("No frames available for the selected trim range")

            for fid in face_ids:
                if fid not in faces_json["faces"]:
                    _update_job(
                        job_id,
                        status="failed",
                        error=f"Unknown face ID: {fid}",
                    )
                    return

            _update_job(
                job_id,
                status="processing",
                progress=0.1,
                phase="extracting_clips",
                message=f"Preparing {len(face_ids)} face(s) across {total_selected_frames} frame(s)",
                completed_frames=0,
                total_frames=total_selected_frames,
            )

            # Phase 1: face_tracker extracts per-face cropped clips
            clips_dir = os.path.join(vdir, "face_clips")
            manifests = await asyncio.get_running_loop().run_in_executor(
                None,
                face_tracker.extract_face_clips,
                frames_dir,
                faces_json,
                face_ids,
                clips_dir,
                resolved_start,
                resolved_end,
            )

            _update_job(job_id, progress=0.3)

            # Phase 2: face_swapper swaps clips + composites back
            def update_progress(p):
                _update_job(job_id, progress=0.3 + p * 0.6)

            def update_status(payload: dict) -> None:
                _update_job(
                    job_id,
                    phase=payload.get("phase"),
                    message=payload.get("message"),
                    completed_frames=payload.get("completed_frames"),
                    total_frames=payload.get("total_frames"),
                )

            engine = face_swapper.create_swap_engine(vdir, style_prompt=style_prompt)
            await asyncio.get_running_loop().run_in_executor(
                None,
                face_swapper.swap_faces_pipeline,
                manifests,
                faces_json,
                frames_dir,
                swapped_dir,
                engine,
                update_progress,
                update_status,
                frame_names,
            )
            reference_warnings = engine.get_warnings()
            if reference_warnings:
                logger.warning("Job %s: reference warnings: %s", job_id, reference_warnings)
                _update_job(job_id, warnings=reference_warnings)

            _update_job(
                job_id,
                progress=0.9,
                phase="rendering",
                message=(
                    f"Rendering {total_selected_frames} frame(s) to video"
                    if media_type == "video"
                    else "Rendering swapped image"
                ),
                completed_frames=total_selected_frames,
                total_frames=total_selected_frames,
            )

            if ENABLE_LIPSYNC and media_type == "video":  # TODO: Non working for now, placeholder
                try:
                    from services.lipsync import apply_lipsync
                    _update_job(
                        job_id,
                        progress=0.9,
                        phase="lipsync",
                        message="Applying lipsync",
                    )
                    first_face = face_ids[0]
                    thumb_path = os.path.join(
                        vdir, faces_json["faces"][first_face]["thumbnail_path"]
                    )
                    audio_path = os.path.join(vdir, "audio.aac")
                    lipsync_output = os.path.join(vdir, "lipsync_output.mp4")

                    if os.path.exists(thumb_path) and os.path.exists(audio_path):
                        apply_lipsync(thumb_path, audio_path, lipsync_output)
                except Exception as e:
                    logger.warning("Lipsync failed (non-fatal): %s", e)

            logger.info("Job %s: >>> preparing render frames", job_id)
            trim_active = resolved_start > 0 or resolved_end < len(_frame_files(frames_dir))
            render_frames_dir = swapped_dir
            if trim_active:
                logger.info("Job %s: staging %d trimmed frames", job_id, len(frame_names))
                _update_job(job_id, progress=0.91, message="Staging trimmed frames")
                render_frames_dir = os.path.join(vdir, "render_frames")
                _stage_frame_sequence(swapped_dir, frame_names, render_frames_dir)
                logger.info("Job %s: staging done", job_id)

            output_path, output_media_type, output_filename = _output_metadata_for_media(
                vdir,
                faces_json,
            )
            if media_type == "image":
                logger.info("Job %s: writing output image", job_id)
                await asyncio.get_running_loop().run_in_executor(
                    None,
                    video.write_image_output,
                    render_frames_dir,
                    output_path,
                )
            else:
                audio_path = os.path.join(vdir, "audio.aac")
                if trim_active:
                    logger.info("Job %s: >>> extracting trimmed audio segment", job_id)
                    original_video = _find_original_media(vdir)
                    trimmed_audio_path = os.path.join(vdir, "audio_trimmed.aac")
                    start_time = resolved_start / max(float(faces_json.get("fps", 30.0)), 1.0)
                    duration = total_selected_frames / max(float(faces_json.get("fps", 30.0)), 1.0)
                    if original_video and video.extract_audio_segment(
                        original_video,
                        trimmed_audio_path,
                        start_time,
                        duration,
                    ):
                        audio_path = trimmed_audio_path
                    else:
                        audio_path = None
                    logger.info("Job %s: <<< audio segment done (audio=%s)", job_id, audio_path)

                logger.info("Job %s: >>> reassembling video from %s (%d frames)", job_id, render_frames_dir, total_selected_frames)
                _update_job(
                    job_id,
                    progress=0.93,
                    phase="rendering",
                    message=f"Encoding final video ({total_selected_frames} frames)",
                )
                t0 = _time.monotonic()

                def _encoding_progress(current_frame: int, total: int) -> None:
                    pct = current_frame / max(1, total)
                    _update_job(
                        job_id,
                        progress=0.93 + pct * 0.06,
                        message=f"Encoding video: {current_frame}/{total} frames",
                    )

                await asyncio.get_running_loop().run_in_executor(
                    None,
                    video.reassemble_video,
                    render_frames_dir,
                    audio_path if audio_path and os.path.exists(audio_path) else None,
                    output_path,
                    faces_json["fps"],
                    _encoding_progress,
                )
                logger.info("Job %s: <<< video encoded in %.1fs", job_id, _time.monotonic() - t0)

            logger.info("Job %s: completed successfully → %s", job_id, output_path)
            _update_job(
                job_id,
                progress=1.0,
                status="completed",
                phase="completed",
                message="Swap complete",
                completed_frames=total_selected_frames,
                total_frames=total_selected_frames,
                output_filename=output_filename,
                output_path=output_path,
                output_media_type=output_media_type,
            )
            if swap_cache_key and swap_cache_request:
                cached_output_path = await asyncio.get_running_loop().run_in_executor(
                    None,
                    _store_cached_swap,
                    vdir,
                    swap_cache_key,
                    swap_cache_request,
                    output_path,
                    output_filename,
                    media_type,
                    output_media_type,
                    reference_warnings,
                )
                _update_job(job_id, cached_output_path=cached_output_path)

        except Exception as e:
            _update_job(job_id, status="failed", error=str(e), phase="failed")


@app.post("/api/swap", response_model=SwapResponse)
async def swap_faces(req: SwapRequest):
    media_id = req.media_id or req.video_id
    vdir = _media_dir(media_id)
    frames_dir = os.path.join(vdir, "frames")
    logger.info(
        "POST /api/swap — video_id=%s, face_ids=%s, style_prompt=%r, frames=[%s:%s]",
        req.video_id, req.face_ids, req.style_prompt, req.start_frame, req.end_frame,
    )

    # Check for uploaded reference image
    uploaded_refs = [f for f in os.listdir(vdir) if f.startswith("uploaded_reference")]
    if uploaded_refs:
        logger.info("Found uploaded reference image: %s", uploaded_refs)
    else:
        logger.info("No uploaded reference image — will use Runware/library/fallback")

    faces_path = os.path.join(vdir, "faces.json")
    if not os.path.exists(faces_path):
        raise HTTPException(status_code=400, detail="Run detect-faces first")

    faces_json = face_tracker.load_faces_json(faces_path)
    media_type = str(faces_json.get("media_type") or "video").lower()
    for fid in req.face_ids:
        if fid not in faces_json["faces"]:
            raise HTTPException(status_code=400, detail=f"Unknown face ID: {fid}")
    if media_type == "image" and (
        req.start_frame is not None or req.end_frame is not None
    ):
        raise HTTPException(
            status_code=400,
            detail="Frame trimming is only supported for video media",
        )
    if req.start_frame is not None and req.start_frame < 0:
        raise HTTPException(status_code=400, detail="start_frame must be >= 0")
    if req.end_frame is not None and req.end_frame <= 0:
        raise HTTPException(status_code=400, detail="end_frame must be > 0")
    if (
        req.start_frame is not None
        and req.end_frame is not None
        and req.end_frame <= req.start_frame
    ):
        raise HTTPException(
            status_code=400,
            detail="end_frame must be greater than start_frame",
        )

    frame_names, resolved_start, resolved_end = _resolve_frame_window(
        frames_dir,
        req.start_frame,
        req.end_frame,
    )
    if not frame_names:
        raise HTTPException(status_code=400, detail="No frames available for the selected trim range")

    swap_request_payload = _swap_cache_request_payload(
        vdir,
        faces_json,
        req.face_ids,
        resolved_start,
        resolved_end,
        req.style_prompt or "",
    )
    swap_key = _swap_cache_key(swap_request_payload)
    cached_swap = _lookup_cached_swap(vdir, swap_key)
    if cached_swap:
        job_id = str(uuid.uuid4())[:8]
        jobs[job_id] = {
            "status": "completed",
            "progress": 1.0,
            "error": None,
            "warnings": cached_swap.get("warnings"),
            "video_id": media_id,
            "media_id": media_id,
            "media_type": cached_swap.get("media_type") or media_type,
            "phase": "completed",
            "message": "Swap loaded from cache",
            "completed_frames": len(frame_names),
            "total_frames": len(frame_names),
            "output_filename": cached_swap.get("output_filename"),
            "output_path": cached_swap.get("output_path"),
            "output_media_type": cached_swap.get("output_media_type") or (
                "image/png" if media_type == "image" else "video/mp4"
            ),
        }
        return SwapResponse(job_id=job_id, media_id=media_id, media_type=media_type)

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "processing",
        "progress": 0.0,
        "error": None,
        "warnings": None,
        "video_id": media_id,
        "media_id": media_id,
        "media_type": media_type,
        "phase": "queued",
        "message": "Waiting to start",
        "completed_frames": 0,
        "total_frames": None,
        "output_filename": None,
        "swap_cache_key": swap_key,
    }

    asyncio.create_task(
        _run_swap_job(
            job_id,
            media_id,
            req.face_ids,
            resolved_start,
            resolved_end,
            req.style_prompt or "",
            swap_key,
            swap_request_payload,
        )
    )

    return SwapResponse(job_id=job_id, media_id=media_id, media_type=media_type)


@app.get("/api/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]

    # Detect stale processing jobs (no progress update for too long)
    if job["status"] == "processing":
        last_updated = job.get("_last_updated")
        if last_updated and (_time.monotonic() - last_updated) > _STALE_JOB_SECONDS:
            logger.error(
                "Job %s: no progress update for %ds, marking as failed",
                job_id, _STALE_JOB_SECONDS,
            )
            job["status"] = "failed"
            job["error"] = (
                f"Job stalled — no progress update for {_STALE_JOB_SECONDS}s. "
                "The swap process may have crashed."
            )
            job["phase"] = "failed"

    return StatusResponse(
        status=job["status"],
        progress=job["progress"],
        error=job.get("error"),
        warnings=job.get("warnings"),
        phase=job.get("phase"),
        message=job.get("message"),
        completed_frames=job.get("completed_frames"),
        total_frames=job.get("total_frames"),
        media_id=job.get("media_id") or job.get("video_id"),
        media_type=job.get("media_type"),
        output_filename=job.get("output_filename"),
    )


@app.post("/api/re-analyze/{job_id}", response_model=UploadResponse)
async def re_analyze(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    if job.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Job is not completed")

    output_path = job.get("output_path")
    if not output_path or not os.path.exists(output_path):
        # Fallback if output_path is not in job dict
        media_id = job.get("media_id") or job.get("video_id")
        if not media_id:
            raise HTTPException(status_code=404, detail="Output file not found")
        vdir = os.path.join(STORAGE_DIR, media_id)
        faces_path = os.path.join(vdir, "faces.json")
        if not os.path.exists(faces_path):
            raise HTTPException(status_code=404, detail="Output file not found")
        faces_json = face_tracker.load_faces_json(faces_path)
        output_path, _, _ = _output_metadata_for_media(vdir, faces_json)

    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail=f"Output file not found at {output_path}")

    # Create new media_id
    ext = os.path.splitext(output_path)[1].lower()
    new_media_id = str(uuid.uuid4())[:8]
    new_media_dir = os.path.join(STORAGE_DIR, new_media_id)
    os.makedirs(new_media_dir, exist_ok=True)

    new_original_path = os.path.join(new_media_dir, f"original{ext}")
    shutil.copy2(output_path, new_original_path)

    media_type = video.media_type_for_path(new_original_path)

    return UploadResponse(video_id=new_media_id, media_id=new_media_id, media_type=media_type)


@app.get("/api/download/{job_id}")
async def download_video(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")

    output_path = job.get("output_path")
    if not output_path:
        faces_path = os.path.join(STORAGE_DIR, job["video_id"], "faces.json")
        if not os.path.exists(faces_path):
            raise HTTPException(status_code=404, detail="Output metadata not found")
        faces_json = face_tracker.load_faces_json(faces_path)
        output_path, output_media_type, output_filename = _output_metadata_for_media(
            os.path.join(STORAGE_DIR, job["video_id"]),
            faces_json,
        )
    else:
        output_media_type = job.get("output_media_type") or "video/mp4"
        output_filename = job.get("output_filename") or "swapped.mp4"
    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="Output file not found")

    return FileResponse(output_path, media_type=output_media_type, filename=output_filename)


@app.delete("/api/job/{job_id}")
async def delete_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    output_path = job.get("output_path")

    # Logic to remove files if they aren't demo/sample files
    if output_path and os.path.exists(output_path):
        path_obj = Path(output_path)
        # Safe check: Only delete if it's in the storage/media_id/swap_cache folder
        try:
            is_in_storage = path_obj.resolve().is_relative_to(Path(STORAGE_DIR).resolve())
            is_in_swap_cache = SWAP_CACHE_DIRNAME in path_obj.parts
            
            if is_in_storage and is_in_swap_cache:
                os.remove(output_path)
                logger.info("Deleted output file for job %s: %s", job_id, output_path)
        except (ValueError, OSError) as e:
            logger.warning("Search/delete failed for job %s: %s", job_id, e)

    del jobs[job_id]
    logger.info("Deleted job metadata for %s", job_id)
    return {"status": "deleted", "job_id": job_id}


if __name__ == "__main__":
    import uvicorn

    os.makedirs(STORAGE_DIR, exist_ok=True)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
