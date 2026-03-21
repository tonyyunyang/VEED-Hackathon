"""
VEED Face Swap API server.

Pipeline:
  1. POST /api/upload          → save video, get video_id
  2. POST /api/detect-faces    → extract frames, detect & cluster faces
  3. POST /api/swap            → for each face: pick source → call FaceFusion
  4. GET  /api/status/{job_id} → poll progress
  5. GET  /api/download/{job_id} → download the swapped video
"""

import os
import uuid
import asyncio

import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from models.schemas import (
    DetectFacesRequest, DetectFacesResponse, FaceInfo,
    StatusResponse, SwapRequest, SwapResponse, UploadResponse,
)
from config import (
    STORAGE_DIR, FRAME_SUBSAMPLE, ENABLE_LIPSYNC,
    FACEFUSION_API_URL, FACEFUSION_SWAP_MODEL,
    FACEFUSION_PIXEL_BOOST, FACEFUSION_ENHANCER,
    FACEFUSION_EXECUTION_PROVIDER, FACEFUSION_VIDEO_QUALITY,
    FACEFUSION_THREAD_COUNT,
)
from services import video, face_tracker
from services.source_picker import pick_source

app = FastAPI(title="VEED Face Swap")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store: job_id → {status, progress, error, video_id}
jobs: dict[str, dict] = {}

POLL_INTERVAL_SECONDS = 2


# ── Helpers ──────────────────────────────────────────────────────────────


def _get_video_dir(video_id: str) -> str:
    """Return the storage directory for a video, or 404."""
    path = os.path.join(STORAGE_DIR, video_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Video not found")
    return path


def _find_original_video(video_dir: str) -> str:
    """Find the uploaded original video file inside a video directory."""
    for filename in os.listdir(video_dir):
        if filename.startswith("original"):
            return os.path.join(video_dir, filename)
    raise HTTPException(status_code=404, detail="Original video not found")


def _resolve_face_crop_path(video_dir: str, face_data: dict) -> str:
    """Return the best available face crop path for source matching.

    Prefers the high-quality padded crop; falls back to the tight thumbnail.
    """
    crop_path = os.path.join(video_dir, face_data["crop_path"])
    if os.path.exists(crop_path):
        return crop_path
    return os.path.join(video_dir, face_data["thumbnail_path"])


def _fail_job(job_id: str, error: str) -> None:
    jobs[job_id] |= {"status": "failed", "error": error}


# ── Upload & detect ──────────────────────────────────────────────────────


@app.post("/api/upload", response_model=UploadResponse)
async def upload_video(file: UploadFile = File(...)):
    """Upload a video file and receive a video_id for subsequent calls."""
    allowed_extensions = {".mp4", ".mov", ".webm", ".avi"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Invalid video format: {ext}")

    video_id = str(uuid.uuid4())[:8]
    video_dir = os.path.join(STORAGE_DIR, video_id)
    os.makedirs(video_dir, exist_ok=True)

    with open(os.path.join(video_dir, f"original{ext}"), "wb") as f:
        f.write(await file.read())

    return UploadResponse(video_id=video_id)


@app.post("/api/detect-faces", response_model=DetectFacesResponse)
async def detect_faces(req: DetectFacesRequest):
    """Extract frames from the video, detect and cluster faces."""
    video_dir = _get_video_dir(req.video_id)
    original_video = _find_original_video(video_dir)
    frames_dir = os.path.join(video_dir, "frames")

    loop = asyncio.get_event_loop()

    # Extract video frames to JPEG files
    video_info = await loop.run_in_executor(
        None, video.extract_frames, original_video, frames_dir
    )

    # Detect and cluster faces across sub-sampled frames
    faces_data = await loop.run_in_executor(
        None, face_tracker.detect_and_cluster, frames_dir, video_dir, FRAME_SUBSAMPLE
    )

    face_tracker.save_faces_json(faces_data, video_info, os.path.join(video_dir, "faces.json"))

    return DetectFacesResponse(
        video_id=req.video_id,
        faces=[
            FaceInfo(
                face_id=face_id,
                thumbnail=data["thumbnail"],
                age=data["age"],
                gender=data["gender"],
                frame_count=data["frame_count"],
            )
            for face_id, data in faces_data["faces"].items()
        ],
    )


# ── FaceFusion API client ───────────────────────────────────────────────


async def _submit_facefusion_swap(
    client: httpx.AsyncClient,
    source_image_path: str,
    target_video_path: str,
) -> str:
    """Upload source + target to FaceFusion /api/swap. Returns the remote job_id."""
    with open(source_image_path, "rb") as source_file, \
         open(target_video_path, "rb") as target_file:
        response = await client.post(
            f"{FACEFUSION_API_URL}/api/swap",
            files={
                "source": (os.path.basename(source_image_path), source_file, "image/jpeg"),
                "target": (os.path.basename(target_video_path), target_file, "video/mp4"),
            },
            data={
                "face_swapper_model": FACEFUSION_SWAP_MODEL,
                "face_swapper_pixel_boost": FACEFUSION_PIXEL_BOOST,
                "face_enhancer": str(FACEFUSION_ENHANCER).lower(),
                "execution_provider": FACEFUSION_EXECUTION_PROVIDER,
                "output_video_quality": str(FACEFUSION_VIDEO_QUALITY),
                "execution_thread_count": str(FACEFUSION_THREAD_COUNT),
                "face_selector_mode": "one",
            },
        )
    if response.status_code != 200:
        raise RuntimeError(f"FaceFusion API error {response.status_code}: {response.text}")
    return response.json()["job_id"]


async def _wait_for_facefusion_job(
    client: httpx.AsyncClient,
    remote_job_id: str,
    local_job_id: str,
    progress_start: float,
    progress_range: float,
) -> None:
    """Poll FaceFusion /api/status until completed, updating local job progress.

    Maps the remote 0→1 progress into the [progress_start, progress_start+progress_range] window.
    """
    while True:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        response = await client.get(f"{FACEFUSION_API_URL}/api/status/{remote_job_id}")
        if response.status_code != 200:
            raise RuntimeError("FaceFusion status check failed")

        remote_status = response.json()
        jobs[local_job_id]["progress"] = progress_start + remote_status["progress"] * progress_range

        if remote_status["status"] == "completed":
            return
        if remote_status["status"] == "failed":
            raise RuntimeError(remote_status.get("error", "FaceFusion processing failed"))


async def _download_facefusion_result(
    client: httpx.AsyncClient,
    remote_job_id: str,
    save_to: str,
) -> None:
    """Download the output video from FaceFusion and clean up the remote job."""
    response = await client.get(f"{FACEFUSION_API_URL}/api/download/{remote_job_id}")
    if response.status_code != 200:
        raise RuntimeError("Failed to download FaceFusion result")
    with open(save_to, "wb") as f:
        f.write(response.content)
    await client.delete(f"{FACEFUSION_API_URL}/api/job/{remote_job_id}")


# ── Swap job (background task) ───────────────────────────────────────────


async def _run_swap_job(local_job_id: str, video_id: str, face_ids: list[str]):
    """Background task: pick sources, chain FaceFusion swaps, optional lipsync.

    For N faces, runs N sequential FaceFusion calls. Each call swaps one face.
    The output of pass i becomes the input of pass i+1, so all faces end up swapped.

    Example with 3 faces:
      Pass 0: source=alice.jpg, target=original.mp4        → swap_pass_0.mp4
      Pass 1: source=bob.jpg,   target=swap_pass_0.mp4     → swap_pass_1.mp4
      Pass 2: source=carol.jpg, target=swap_pass_1.mp4     → swap_pass_2.mp4 → output.mp4
    """
    try:
        video_dir = os.path.join(STORAGE_DIR, video_id)
        faces_json = face_tracker.load_faces_json(os.path.join(video_dir, "faces.json"))

        # Validate all face IDs upfront
        for face_id in face_ids:
            if face_id not in faces_json["faces"]:
                _fail_job(local_job_id, f"Unknown face ID: {face_id}")
                return

        jobs[local_job_id] |= {"status": "processing", "progress": 0.05}

        original_video = None
        for filename in os.listdir(video_dir):
            if filename.startswith("original"):
                original_video = os.path.join(video_dir, filename)
                break
        if not original_video:
            _fail_job(local_job_id, "Original video not found")
            return

        # ── Step 1: Pick a source image for each face ────────────────────
        # Compares each person's face crop against picture_example/ library.
        source_image_per_face: dict[str, str] = {}
        for face_id in face_ids:
            face_data = faces_json["faces"][face_id]
            face_crop_path = _resolve_face_crop_path(video_dir, face_data)
            source_image_per_face[face_id] = pick_source(face_crop_path)

        jobs[local_job_id]["progress"] = 0.10

        # ── Step 2: Chain FaceFusion swap calls (one per face) ───────────
        # Budget: 10%→(80% or 95%) for swaps, rest for lipsync.
        num_faces = len(face_ids)
        lipsync_budget = 0.15 if ENABLE_LIPSYNC else 0.0
        total_swap_budget = 0.85 - lipsync_budget  # e.g. 0.70 with lipsync, 0.85 without
        per_face_budget = total_swap_budget / num_faces

        current_video = original_video  # input to the next swap pass

        async with httpx.AsyncClient(timeout=None) as client:
            for pass_index, face_id in enumerate(face_ids):
                source_image = source_image_per_face[face_id]
                pass_output = os.path.join(video_dir, f"swap_pass_{pass_index}.mp4")
                progress_start = 0.10 + pass_index * per_face_budget

                remote_job_id = await _submit_facefusion_swap(client, source_image, current_video)
                await _wait_for_facefusion_job(
                    client, remote_job_id, local_job_id, progress_start, per_face_budget
                )
                await _download_facefusion_result(client, remote_job_id, pass_output)

                current_video = pass_output  # feed into next pass

            # current_video now contains all faces swapped
            final_output = os.path.join(video_dir, "output.mp4")

            # ── Step 3 (optional): Lipsync pass ─────────────────────────
            if ENABLE_LIPSYNC:
                jobs[local_job_id]["progress"] = 0.80

                with open(original_video, "rb") as audio_file, \
                     open(current_video, "rb") as swapped_file:
                    lipsync_response = await client.post(
                        f"{FACEFUSION_API_URL}/api/lipsync",
                        files={
                            "audio": (os.path.basename(original_video), audio_file, "video/mp4"),
                            "target": ("swapped.mp4", swapped_file, "video/mp4"),
                        },
                        data={
                            "execution_provider": FACEFUSION_EXECUTION_PROVIDER,
                            "output_video_quality": str(FACEFUSION_VIDEO_QUALITY),
                            "execution_thread_count": str(FACEFUSION_THREAD_COUNT),
                        },
                    )

                if lipsync_response.status_code != 200:
                    # Lipsync failure is non-fatal — use swap-only output
                    os.rename(current_video, final_output)
                else:
                    lipsync_job_id = lipsync_response.json()["job_id"]
                    try:
                        await _wait_for_facefusion_job(
                            client, lipsync_job_id, local_job_id, 0.80, 0.15
                        )
                        await _download_facefusion_result(client, lipsync_job_id, final_output)
                    except RuntimeError:
                        # Lipsync failure is non-fatal
                        os.rename(current_video, final_output)
            else:
                os.rename(current_video, final_output)

            # Clean up intermediate swap pass files
            for i in range(num_faces):
                intermediate = os.path.join(video_dir, f"swap_pass_{i}.mp4")
                if intermediate != final_output and os.path.exists(intermediate):
                    os.remove(intermediate)

        jobs[local_job_id] |= {"progress": 1.0, "status": "completed"}

    except Exception as e:
        _fail_job(local_job_id, str(e))


# ── Swap / status / download endpoints ───────────────────────────────────


@app.post("/api/swap", response_model=SwapResponse)
async def swap_faces(req: SwapRequest):
    """Start a face-swap job. Returns a job_id to poll for progress."""
    video_dir = _get_video_dir(req.video_id)
    faces_path = os.path.join(video_dir, "faces.json")
    if not os.path.exists(faces_path):
        raise HTTPException(status_code=400, detail="Run detect-faces first")

    faces_json = face_tracker.load_faces_json(faces_path)
    for face_id in req.face_ids:
        if face_id not in faces_json["faces"]:
            raise HTTPException(status_code=400, detail=f"Unknown face ID: {face_id}")

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "pending",
        "progress": 0.0,
        "error": None,
        "video_id": req.video_id,
    }
    asyncio.create_task(_run_swap_job(job_id, req.video_id, req.face_ids))
    return SwapResponse(job_id=job_id)


@app.get("/api/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str):
    """Poll the progress of a swap job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    return StatusResponse(status=job["status"], progress=job["progress"], error=job.get("error"))


@app.get("/api/download/{job_id}")
async def download_video(job_id: str):
    """Download the finished swapped video."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")

    output_path = os.path.join(STORAGE_DIR, job["video_id"], "output.mp4")
    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="Output file not found")
    return FileResponse(output_path, media_type="video/mp4", filename="swapped.mp4")


# ── Entrypoint ───────────────────────────────────────────────────────────


if __name__ == "__main__":
    import uvicorn

    os.makedirs(STORAGE_DIR, exist_ok=True)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
