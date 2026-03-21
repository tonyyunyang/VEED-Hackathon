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

app = FastAPI(title="VEED Face Swap")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

jobs: dict[str, dict] = {}


def _video_dir(video_id: str) -> str:
    path = os.path.join(STORAGE_DIR, video_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Video not found")
    return path


def _find_original(vdir: str) -> str:
    for f in os.listdir(vdir):
        if f.startswith("original"):
            return os.path.join(vdir, f)
    raise HTTPException(status_code=404, detail="Original video not found")


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
        f.write(await file.read())

    return UploadResponse(video_id=video_id)


@app.post("/api/detect-faces", response_model=DetectFacesResponse)
async def detect_faces(req: DetectFacesRequest):
    vdir = _video_dir(req.video_id)
    original = _find_original(vdir)
    frames_dir = os.path.join(vdir, "frames")

    loop = asyncio.get_event_loop()
    video_info = await loop.run_in_executor(None, video.extract_frames, original, frames_dir)
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
    try:
        vdir = os.path.join(STORAGE_DIR, video_id)
        faces_json = face_tracker.load_faces_json(os.path.join(vdir, "faces.json"))

        for fid in face_ids:
            if fid not in faces_json["faces"]:
                jobs[job_id] |= {"status": "failed", "error": f"Unknown face ID: {fid}"}
                return

        jobs[job_id] |= {"status": "processing", "progress": 0.05}

        original = None
        for f in os.listdir(vdir):
            if f.startswith("original"):
                original = os.path.join(vdir, f)
                break
        if not original:
            jobs[job_id] |= {"status": "failed", "error": "Original video not found"}
            return

        # Resolve source face image — may be absolute (library) or relative (crop)
        face_data = faces_json["faces"][face_ids[0]]
        raw_source = face_data["source_path"]
        source_path = raw_source if os.path.isabs(raw_source) else os.path.join(vdir, raw_source)
        if not os.path.exists(source_path):
            source_path = os.path.join(vdir, face_data["thumbnail_path"])
        if not os.path.exists(source_path):
            jobs[job_id] |= {"status": "failed", "error": "Source face image not found"}
            return

        jobs[job_id]["progress"] = 0.1

        # Call FaceFusion API
        async with httpx.AsyncClient(timeout=None) as client:
            with open(source_path, "rb") as src_f, open(original, "rb") as tgt_f:
                resp = await client.post(
                    f"{FACEFUSION_API_URL}/api/swap",
                    files={
                        "source": (os.path.basename(source_path), src_f, "image/jpeg"),
                        "target": (os.path.basename(original), tgt_f, "video/mp4"),
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

            if resp.status_code != 200:
                jobs[job_id] |= {
                    "status": "failed",
                    "error": f"FaceFusion API error {resp.status_code}: {resp.text}",
                }
                return

            ff_job_id = resp.json()["job_id"]

            # Poll for progress
            while True:
                await asyncio.sleep(2)
                status_resp = await client.get(f"{FACEFUSION_API_URL}/api/status/{ff_job_id}")
                if status_resp.status_code != 200:
                    jobs[job_id] |= {"status": "failed", "error": "FaceFusion status check failed"}
                    return

                ff = status_resp.json()
                swap_weight = 0.65 if ENABLE_LIPSYNC else 0.85
                jobs[job_id]["progress"] = 0.1 + ff["progress"] * swap_weight

                if ff["status"] == "completed":
                    break
                if ff["status"] == "failed":
                    jobs[job_id] |= {
                        "status": "failed",
                        "error": ff.get("error", "FaceFusion processing failed"),
                    }
                    return

            # Download swap result
            swap_output = os.path.join(vdir, "swap_output.mp4")
            dl = await client.get(f"{FACEFUSION_API_URL}/api/download/{ff_job_id}")
            if dl.status_code != 200:
                jobs[job_id] |= {"status": "failed", "error": "Failed to download result"}
                return

            with open(swap_output, "wb") as out_f:
                out_f.write(dl.content)

            # Cleanup remote swap job
            await client.delete(f"{FACEFUSION_API_URL}/api/job/{ff_job_id}")

            output_path = os.path.join(vdir, "output.mp4")

            # Lipsync pass (uses original audio + swapped video)
            if ENABLE_LIPSYNC:
                jobs[job_id]["progress"] = 0.80

                with open(original, "rb") as audio_f, open(swap_output, "rb") as vid_f:
                    ls_resp = await client.post(
                        f"{FACEFUSION_API_URL}/api/lipsync",
                        files={
                            "audio": (os.path.basename(original), audio_f, "video/mp4"),
                            "target": ("swap_output.mp4", vid_f, "video/mp4"),
                        },
                        data={
                            "execution_provider": FACEFUSION_EXECUTION_PROVIDER,
                            "output_video_quality": str(FACEFUSION_VIDEO_QUALITY),
                            "execution_thread_count": str(FACEFUSION_THREAD_COUNT),
                        },
                    )

                if ls_resp.status_code != 200:
                    # Lipsync failure is non-fatal — fall back to swap-only output
                    os.rename(swap_output, output_path)
                else:
                    ls_job_id = ls_resp.json()["job_id"]

                    while True:
                        await asyncio.sleep(2)
                        ls_status = await client.get(f"{FACEFUSION_API_URL}/api/status/{ls_job_id}")
                        if ls_status.status_code != 200:
                            os.rename(swap_output, output_path)
                            break
                        ls = ls_status.json()
                        jobs[job_id]["progress"] = 0.80 + ls["progress"] * 0.15

                        if ls["status"] == "completed":
                            ls_dl = await client.get(f"{FACEFUSION_API_URL}/api/download/{ls_job_id}")
                            if ls_dl.status_code == 200:
                                with open(output_path, "wb") as out_f:
                                    out_f.write(ls_dl.content)
                            else:
                                os.rename(swap_output, output_path)
                            await client.delete(f"{FACEFUSION_API_URL}/api/job/{ls_job_id}")
                            break
                        if ls["status"] == "failed":
                            # Non-fatal — use swap output
                            os.rename(swap_output, output_path)
                            await client.delete(f"{FACEFUSION_API_URL}/api/job/{ls_job_id}")
                            break
            else:
                os.rename(swap_output, output_path)

        jobs[job_id] |= {"progress": 1.0, "status": "completed"}

    except Exception as e:
        jobs[job_id] |= {"status": "failed", "error": str(e)}


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
    jobs[job_id] = {"status": "pending", "progress": 0.0, "error": None, "video_id": req.video_id}
    asyncio.create_task(_run_swap_job(job_id, req.video_id, req.face_ids))
    return SwapResponse(job_id=job_id)


@app.get("/api/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    j = jobs[job_id]
    return StatusResponse(status=j["status"], progress=j["progress"], error=j.get("error"))


@app.get("/api/download/{job_id}")
async def download_video(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    j = jobs[job_id]
    if j["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")

    output_path = os.path.join(STORAGE_DIR, j["video_id"], "output.mp4")
    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="Output file not found")
    return FileResponse(output_path, media_type="video/mp4", filename="swapped.mp4")


if __name__ == "__main__":
    import uvicorn

    os.makedirs(STORAGE_DIR, exist_ok=True)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
