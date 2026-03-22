import os
import uuid
import asyncio
import shutil

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from models.schemas import (
    DetectFacesRequest, DetectFacesResponse, FaceInfo,
    StatusResponse, SwapRequest, SwapResponse, UploadResponse,
)
from config import (
    DUMMY_TRACKING,
    STORAGE_DIR,
    ENABLE_LIPSYNC,
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


def _video_dir(video_id: str) -> str:
    path = os.path.join(STORAGE_DIR, video_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Video not found")
    return path


def _find_original_video(video_dir: str) -> str | None:
    for file_name in os.listdir(video_dir):
        if file_name.startswith("original"):
            return os.path.join(video_dir, file_name)
    return None


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
    jobs[job_id].update(fields)


@app.post("/api/upload", response_model=UploadResponse)
async def upload_video(file: UploadFile = File(...)):
    allowed = {".mp4", ".mov", ".webm", ".avi"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid video format: {ext}")

    video_id = str(uuid.uuid4())[:8]
    video_dir = os.path.join(STORAGE_DIR, video_id)
    os.makedirs(video_dir, exist_ok=True)

    video_path = os.path.join(video_dir, f"original{ext}")
    with open(video_path, "wb") as f:
        content = await file.read()
        f.write(content)

    return UploadResponse(video_id=video_id)


@app.post("/api/detect-faces", response_model=DetectFacesResponse)
async def detect_faces(req: DetectFacesRequest):
    vdir = _video_dir(req.video_id)

    original = None
    for f in os.listdir(vdir):
        if f.startswith("original"):
            original = os.path.join(vdir, f)
            break
    if not original:
        raise HTTPException(status_code=404, detail="Original video not found")

    frames_dir = os.path.join(vdir, "frames")

    loop = asyncio.get_running_loop()
    video_info = await loop.run_in_executor(
        None, video.extract_frames, original, frames_dir
    )

    audio_path = os.path.join(vdir, "audio.aac")
    await loop.run_in_executor(None, video.extract_audio, original, audio_path)

    faces_data = await loop.run_in_executor(
        None, face_tracker.detect_and_cluster, frames_dir, vdir, FRAME_SUBSAMPLE
    )
    face_tracker.save_faces_json(faces_data, video_info, os.path.join(vdir, "faces.json"))

    faces_list = [
        FaceInfo(
            face_id=fid,
            thumbnail=fdata["thumbnail"],
            age=fdata["age"],
            gender=fdata["gender"],
            frame_count=fdata["frame_count"],
            frames=fdata.get("frames", {}),
        )
        for fid, fdata in faces_data["faces"].items()
    ]

    return DetectFacesResponse(
        video_id=req.video_id,
        fps=video_info["fps"],
        faces=faces_list,
    )


async def _run_swap_job(
    job_id: str,
    video_id: str,
    face_ids: list[str],
    start_frame: int | None = None,
    end_frame: int | None = None,
):
    async with swap_lock:  # TODO do I need a lock for the //?
        try:
            vdir = os.path.join(STORAGE_DIR, video_id)
            frames_dir = os.path.join(vdir, "frames")
            swapped_dir = os.path.join(vdir, "swapped")
            faces_json = face_tracker.load_faces_json(os.path.join(vdir, "faces.json"))
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
                _update_job(job_id, progress=0.3 + p * 0.5)

            def update_status(payload: dict) -> None:
                _update_job(
                    job_id,
                    phase=payload.get("phase"),
                    message=payload.get("message"),
                    completed_frames=payload.get("completed_frames"),
                    total_frames=payload.get("total_frames"),
                )

            engine = face_swapper.create_swap_engine(vdir)
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

            _update_job(
                job_id,
                progress=0.8,
                phase="rendering",
                message=f"Rendering {total_selected_frames} frame(s) to video",
                completed_frames=total_selected_frames,
                total_frames=total_selected_frames,
            )

            if ENABLE_LIPSYNC:  # TODO: Non working for now, placeholder
                try:
                    from services.lipsync import apply_lipsync
                    _update_job(
                        job_id,
                        progress=0.85,
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
                        _update_job(job_id, progress=0.9)
                except Exception as e:
                    print(f"Lipsync failed (non-fatal): {e}")

            trim_active = resolved_start > 0 or resolved_end < len(_frame_files(frames_dir))
            render_frames_dir = swapped_dir
            if trim_active:
                render_frames_dir = os.path.join(vdir, "render_frames")
                _stage_frame_sequence(swapped_dir, frame_names, render_frames_dir)

            audio_path = os.path.join(vdir, "audio.aac")
            if trim_active:
                original_video = _find_original_video(vdir)
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

            output_path = os.path.join(vdir, "output.mp4")
            await asyncio.get_running_loop().run_in_executor(
                None,
                video.reassemble_video,
                render_frames_dir,
                audio_path if audio_path and os.path.exists(audio_path) else None,
                output_path,
                faces_json["fps"],
            )

            _update_job(
                job_id,
                progress=1.0,
                status="completed",
                phase="completed",
                message="Swap complete",
                completed_frames=total_selected_frames,
                total_frames=total_selected_frames,
            )

        except Exception as e:
            _update_job(job_id, status="failed", error=str(e), phase="failed")


@app.post("/api/swap", response_model=SwapResponse)
async def swap_faces(req: SwapRequest):
    vdir = _video_dir(req.video_id)

    faces_path = os.path.join(vdir, "faces.json")
    if not os.path.exists(faces_path):
        raise HTTPException(status_code=400, detail="Run detect-faces first")

    faces_json = face_tracker.load_faces_json(faces_path)
    for fid in req.face_ids:
        if fid not in faces_json["faces"]:
            raise HTTPException(status_code=400, detail=f"Unknown face ID: {fid}")
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

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "processing",
        "progress": 0.0,
        "error": None,
        "video_id": req.video_id,
        "phase": "queued",
        "message": "Waiting to start",
        "completed_frames": 0,
        "total_frames": None,
    }

    asyncio.create_task(
        _run_swap_job(
            job_id,
            req.video_id,
            req.face_ids,
            req.start_frame,
            req.end_frame,
        )
    )

    return SwapResponse(job_id=job_id)


@app.get("/api/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    return StatusResponse(
        status=job["status"],
        progress=job["progress"],
        error=job.get("error"),
        phase=job.get("phase"),
        message=job.get("message"),
        completed_frames=job.get("completed_frames"),
        total_frames=job.get("total_frames"),
    )


@app.get("/api/download/{job_id}")
async def download_video(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")

    output_path = os.path.join(STORAGE_DIR, job["video_id"], "output.mp4")
    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="Output file not found")

    return FileResponse(output_path, media_type="video/mp4", filename="swapped.mp4")


if __name__ == "__main__":
    import uvicorn

    os.makedirs(STORAGE_DIR, exist_ok=True)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
