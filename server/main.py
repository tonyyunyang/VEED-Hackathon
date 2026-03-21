import os
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from models.schemas import (
    DetectFacesRequest, DetectFacesResponse, FaceInfo,
    StatusResponse, SwapRequest, SwapResponse, UploadResponse,
)
from config import STORAGE_DIR, ENABLE_LIPSYNC, FRAME_SUBSAMPLE
from services import video, face_tracker, face_swapper

app = FastAPI(title="VEED Face Swap")

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

    loop = asyncio.get_event_loop()
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
        )
        for fid, fdata in faces_data["faces"].items()
    ]

    return DetectFacesResponse(video_id=req.video_id, faces=faces_list)


async def _run_swap_job(job_id: str, video_id: str, face_ids: list[str]):
    async with swap_lock:
        try:
            vdir = os.path.join(STORAGE_DIR, video_id)
            frames_dir = os.path.join(vdir, "frames")
            swapped_dir = os.path.join(vdir, "swapped")
            faces_json = face_tracker.load_faces_json(os.path.join(vdir, "faces.json"))

            for fid in face_ids:
                if fid not in faces_json["faces"]:
                    jobs[job_id]["status"] = "failed"
                    jobs[job_id]["error"] = f"Unknown face ID: {fid}"
                    return

            jobs[job_id]["status"] = "processing"
            jobs[job_id]["progress"] = 0.1

            def update_progress(p):
                jobs[job_id]["progress"] = 0.1 + p * 0.7

            adapter = face_swapper.InsightFaceSwapAdapter()
            await asyncio.get_event_loop().run_in_executor(
                None,
                face_swapper.swap_faces_in_video,
                frames_dir,
                swapped_dir,
                faces_json,
                face_ids,
                adapter,
                update_progress,
            )

            jobs[job_id]["progress"] = 0.8

            if ENABLE_LIPSYNC:
                try:
                    from services.lipsync import apply_lipsync
                    jobs[job_id]["progress"] = 0.85
                    first_face = face_ids[0]
                    thumb_path = os.path.join(
                        vdir, faces_json["faces"][first_face]["thumbnail_path"]
                    )
                    audio_path = os.path.join(vdir, "audio.aac")
                    lipsync_output = os.path.join(vdir, "lipsync_output.mp4")

                    if os.path.exists(thumb_path) and os.path.exists(audio_path):
                        apply_lipsync(thumb_path, audio_path, lipsync_output)
                        jobs[job_id]["progress"] = 0.9
                except Exception as e:
                    print(f"Lipsync failed (non-fatal): {e}")

            audio_path = os.path.join(vdir, "audio.aac")
            output_path = os.path.join(vdir, "output.mp4")
            await asyncio.get_event_loop().run_in_executor(
                None,
                video.reassemble_video,
                swapped_dir,
                audio_path if os.path.exists(audio_path) else None,
                output_path,
                faces_json["fps"],
            )

            jobs[job_id]["progress"] = 1.0
            jobs[job_id]["status"] = "completed"

        except Exception as e:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(e)


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

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "processing",
        "progress": 0.0,
        "error": None,
        "video_id": req.video_id,
    }

    asyncio.create_task(_run_swap_job(job_id, req.video_id, req.face_ids))

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
