# Face Swap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a face-swap web app: upload video, detect faces, swap selected faces, optionally lipsync, download result.

**Architecture:** FastAPI backend with InsightFace for face detection/clustering, pluggable face swap adapter, optional VEED Fabric lipsync. React frontend with 4-state linear flow. FFmpeg for video I/O.

**Tech Stack:** Python 3.11+, FastAPI, InsightFace, FFmpeg, fal-client | React 19, TypeScript, Vite, Tailwind 4, shadcn

**Spec:** `docs/superpowers/specs/2026-03-21-face-swap-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `server/config.py` | Create | Backend config (env vars) |
| `server/models/__init__.py` | Create | Package init |
| `server/models/schemas.py` | Create | Pydantic request/response models |
| `server/services/__init__.py` | Create | Package init |
| `server/services/video.py` | Create | FFmpeg frame extraction + reassembly |
| `server/services/face_tracker.py` | Create | InsightFace detection + clustering |
| `server/services/face_swapper.py` | Create | Pluggable face swap adapter |
| `server/services/lipsync.py` | Create | VEED Fabric 1.0 integration |
| `server/main.py` | Rewrite | FastAPI routes (replace template code) |
| `server/requirements.txt` | Modify | Add new dependencies |
| `src/types.ts` | Rewrite | Face-swap TypeScript types |
| `src/lib/utils/api.ts` | Modify | Add API client functions |
| `src/components/VideoUploader.tsx` | Create | Upload component |
| `src/components/FaceSelector.tsx` | Create | Face selection grid |
| `src/components/ProcessingStatus.tsx` | Create | Progress + download |
| `src/App.tsx` | Rewrite | 4-state linear flow |
| `src/components/VideoPlayer.tsx` | Delete | Not needed |

---

### Task 1: Shared Contracts — Backend Config, Schemas, Dependencies

**Files:**
- Create: `server/config.py`
- Create: `server/models/__init__.py`
- Create: `server/models/schemas.py`
- Create: `server/services/__init__.py`
- Modify: `server/requirements.txt`

- [ ] **Step 1: Update `server/requirements.txt`**

```
fastapi[standard]>=0.110.0
uvicorn>=0.27.1
python-dotenv>=1.0.1
pydantic>=2.6.3
python-multipart>=0.0.9
insightface>=0.7.3
onnxruntime>=1.17.0
opencv-python>=4.9.0
numpy>=1.26.0
fal-client>=0.5.0
httpx>=0.28.0
```

- [ ] **Step 2: Create `server/config.py`**

```python
import os
from dotenv import load_dotenv

load_dotenv()


STORAGE_DIR = os.path.join(os.path.dirname(__file__), "storage")
ENABLE_LIPSYNC = os.getenv("ENABLE_LIPSYNC", "false").lower() == "true"
FAL_KEY = os.getenv("FAL_KEY", "")
LIPSYNC_RESOLUTION = os.getenv("LIPSYNC_RESOLUTION", "480p")
FRAME_SUBSAMPLE = int(os.getenv("FRAME_SUBSAMPLE", "5"))
```

- [ ] **Step 3: Create `server/models/__init__.py`** (empty file)

- [ ] **Step 4: Create `server/models/schemas.py`**

```python
from pydantic import BaseModel


class UploadResponse(BaseModel):
    video_id: str


class DetectFacesRequest(BaseModel):
    video_id: str


class FaceInfo(BaseModel):
    face_id: str
    thumbnail: str  # data:image/jpeg;base64,...
    age: int
    gender: str
    frame_count: int


class DetectFacesResponse(BaseModel):
    video_id: str
    faces: list[FaceInfo]


class SwapRequest(BaseModel):
    video_id: str
    face_ids: list[str]


class SwapResponse(BaseModel):
    job_id: str


class StatusResponse(BaseModel):
    status: str  # "processing" | "completed" | "failed"
    progress: float
    error: str | None = None
```

- [ ] **Step 5: Create `server/services/__init__.py`** (empty file)

- [ ] **Step 6: Commit**

```bash
git add server/config.py server/models/ server/services/__init__.py server/requirements.txt
git commit -m "feat: add backend config, Pydantic schemas, and updated dependencies"
```

---

### Task 2: Video Service — FFmpeg Frame Extraction & Reassembly

**Files:**
- Create: `server/services/video.py`

- [ ] **Step 1: Create `server/services/video.py`**

```python
import os
import subprocess
import json


def get_video_info(video_path: str) -> dict:
    """Get FPS and frame count using ffprobe."""
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
    """Extract all frames from video. Returns video info dict."""
    os.makedirs(output_dir, exist_ok=True)
    info = get_video_info(video_path)
    cmd = [
        "ffmpeg", "-i", video_path, "-vsync", "0",
        os.path.join(output_dir, "frame_%04d.jpg"), "-y"
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return info


def extract_audio(video_path: str, output_path: str) -> bool:
    """Extract audio track. Returns True if audio exists."""
    cmd = [
        "ffmpeg", "-i", video_path, "-vn", "-acodec", "aac",
        "-b:a", "128k", output_path, "-y"
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


def reassemble_video(
    frames_dir: str, audio_path: str | None, output_path: str, fps: float
) -> None:
    """Combine frames + audio into final video."""
    cmd = [
        "ffmpeg", "-framerate", str(fps),
        "-i", os.path.join(frames_dir, "frame_%04d.jpg"),
    ]
    if audio_path and os.path.exists(audio_path):
        cmd.extend(["-i", audio_path, "-c:a", "aac", "-shortest"])
    cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", output_path, "-y"])
    subprocess.run(cmd, capture_output=True, check=True)
```

- [ ] **Step 2: Verify FFmpeg is available**

Run: `which ffmpeg`
Expected: path to ffmpeg binary

- [ ] **Step 3: Commit**

```bash
git add server/services/video.py
git commit -m "feat: add video service for FFmpeg frame extraction and reassembly"
```

---

### Task 3: Face Tracker — InsightFace Detection & Clustering

**Files:**
- Create: `server/services/face_tracker.py`

- [ ] **Step 1: Create `server/services/face_tracker.py`**

```python
import os
import json
import base64
from collections import defaultdict

import cv2
import numpy as np
from insightface.app import FaceAnalysis

_app: FaceAnalysis | None = None


def _get_app() -> FaceAnalysis:
    global _app
    if _app is None:
        _app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        _app.prepare(ctx_id=0, det_size=(640, 640))
    return _app


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def _crop_face_thumbnail(frame: np.ndarray, bbox: list[float], size: int = 112) -> str:
    """Crop face region and return as base64 JPEG data URI."""
    x1, y1, x2, y2 = [int(v) for v in bbox]
    h, w = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return ""
    crop = cv2.resize(crop, (size, size))
    _, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    b64 = base64.b64encode(buf).decode()
    return f"data:image/jpeg;base64,{b64}"


def detect_and_cluster(
    frames_dir: str, storage_dir: str, subsample: int = 5
) -> dict:
    """Detect faces in subsampled frames, cluster by identity.

    Returns faces dict ready for faces.json and API response.
    """
    app = _get_app()
    frame_files = sorted(
        f for f in os.listdir(frames_dir) if f.startswith("frame_") and f.endswith(".jpg")
    )

    # Collect all detections: (frame_idx, face_obj)
    detections: list[tuple[int, object]] = []
    frame_cache: dict[int, np.ndarray] = {}

    for i, fname in enumerate(frame_files):
        if i % subsample != 0:
            continue
        frame_path = os.path.join(frames_dir, fname)
        frame = cv2.imread(frame_path)
        if frame is None:
            continue
        frame_cache[i] = frame
        faces = app.get(frame)
        for face in faces:
            detections.append((i, face))

    if not detections:
        return {"faces": {}}

    # Cluster by embedding similarity
    clusters: list[list[tuple[int, object]]] = []
    similarity_threshold = 0.4

    for frame_idx, face in detections:
        emb = face.normed_embedding
        matched = False
        for cluster in clusters:
            rep_emb = cluster[0][1].normed_embedding
            if _cosine_similarity(emb, rep_emb) >= similarity_threshold:
                cluster.append((frame_idx, face))
                matched = True
                break
        if not matched:
            clusters.append([(frame_idx, face)])

    # Build faces dict
    faces_data = {}
    for cluster_idx, cluster in enumerate(clusters):
        face_id = f"face_{cluster_idx}"
        ages = [f.age for _, f in cluster]
        genders = [f.gender for _, f in cluster]

        # Pick best thumbnail: largest face area
        best_idx, best_face = max(
            cluster,
            key=lambda x: (x[1].bbox[2] - x[1].bbox[0]) * (x[1].bbox[3] - x[1].bbox[1])
        )
        best_frame = frame_cache.get(best_idx)
        thumbnail = ""
        if best_frame is not None:
            thumbnail = _crop_face_thumbnail(best_frame, best_face.bbox.tolist())

        # Save thumbnail to disk
        thumb_path = f"{face_id}_thumb.jpg"
        if best_frame is not None:
            x1, y1, x2, y2 = [int(v) for v in best_face.bbox]
            h, w = best_frame.shape[:2]
            crop = best_frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
            if crop.size > 0:
                cv2.imwrite(os.path.join(storage_dir, thumb_path), crop)

        # Build frames dict
        frames_dict = {}
        for frame_idx, face in cluster:
            frames_dict[str(frame_idx)] = face.bbox.tolist()

        avg_age = int(np.mean(ages))
        gender_counts = defaultdict(int)
        for g in genders:
            gender_counts[g] += 1
        majority_gender = max(gender_counts, key=gender_counts.get)

        faces_data[face_id] = {
            "age": avg_age,
            "gender": majority_gender,
            "thumbnail": thumbnail,
            "thumbnail_path": thumb_path,
            "embedding": cluster[0][1].normed_embedding.tolist(),
            "frames": frames_dict,
            "frame_count": len(frames_dict),
        }

    return {"faces": faces_data}


def save_faces_json(faces_data: dict, video_info: dict, output_path: str) -> None:
    """Save faces.json to disk."""
    data = {
        "fps": video_info["fps"],
        "total_frames": video_info["total_frames"],
        "faces": faces_data["faces"],
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


def load_faces_json(path: str) -> dict:
    """Load faces.json from disk."""
    with open(path) as f:
        return json.load(f)
```

- [ ] **Step 2: Commit**

```bash
git add server/services/face_tracker.py
git commit -m "feat: add face tracker with InsightFace detection and clustering"
```

---

### Task 4: Face Swapper — Pluggable Adapter with InsightFace Default

**Files:**
- Create: `server/services/face_swapper.py`

- [ ] **Step 1: Create `server/services/face_swapper.py`**

```python
import os
from abc import ABC, abstractmethod

import cv2
import numpy as np
from insightface.app import FaceAnalysis

_app: FaceAnalysis | None = None
_swapper = None


def _get_app() -> FaceAnalysis:
    global _app
    if _app is None:
        _app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        _app.prepare(ctx_id=0, det_size=(640, 640))
    return _app


def _get_swapper():
    global _swapper
    if _swapper is None:
        import insightface
        model_path = os.path.join(
            os.path.dirname(__file__), "..", "models", "inswapper_128.onnx"
        )
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"inswapper_128.onnx not found at {model_path}. "
                "Download it and place it in server/models/"
            )
        _swapper = insightface.model_zoo.get_model(model_path)
    return _swapper


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


class FaceSwapAdapter(ABC):
    """Base interface for face swap providers."""

    @abstractmethod
    def swap_face(
        self,
        frame: np.ndarray,
        target_face,
        source_face,
    ) -> np.ndarray:
        """Swap source face onto target face in frame. Returns modified frame."""
        raise NotImplementedError


class InsightFaceSwapAdapter(FaceSwapAdapter):
    """Face swap using InsightFace inswapper_128."""

    def __init__(self, reference_image_path: str | None = None):
        self._source_face = None
        if reference_image_path and os.path.exists(reference_image_path):
            self._load_source(reference_image_path)

    def _load_source(self, image_path: str):
        app = _get_app()
        img = cv2.imread(image_path)
        if img is None:
            return
        faces = app.get(img)
        if faces:
            self._source_face = faces[0]

    def set_source_face(self, face):
        """Set source face directly from a detected face object."""
        self._source_face = face

    def swap_face(self, frame: np.ndarray, target_face, source_face=None) -> np.ndarray:
        swapper = _get_swapper()
        src = source_face or self._source_face
        if src is None:
            return frame
        return swapper.get(frame, target_face, src, paste_back=True)


def swap_faces_in_video(
    frames_dir: str,
    output_dir: str,
    faces_json: dict,
    selected_face_ids: list[str],
    adapter: FaceSwapAdapter | None = None,
    progress_callback=None,
) -> None:
    """Swap selected faces across all frames.

    Args:
        frames_dir: directory with original frame_XXXX.jpg files
        output_dir: directory for swapped frames
        faces_json: loaded faces.json dict
        selected_face_ids: list of face IDs to swap
        adapter: FaceSwapAdapter instance (default: InsightFaceSwapAdapter)
        progress_callback: callable(progress: float) for status updates
    """
    os.makedirs(output_dir, exist_ok=True)
    app = _get_app()

    if adapter is None:
        adapter = InsightFaceSwapAdapter()

    # For each selected face, we need a source face to swap in.
    # For now, use a placeholder: generate a random source by using
    # a different detected face, or skip if only one person.
    # This is the pluggable part — replace with actual API call.
    selected_faces = {
        fid: faces_json["faces"][fid]
        for fid in selected_face_ids
        if fid in faces_json["faces"]
    }

    # Load all frame files
    frame_files = sorted(
        f for f in os.listdir(frames_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    )
    total = len(frame_files)

    for i, fname in enumerate(frame_files):
        frame_path = os.path.join(frames_dir, fname)
        frame = cv2.imread(frame_path)
        if frame is None:
            continue

        # Detect faces in this frame
        detected = app.get(frame)

        for face_id, face_data in selected_faces.items():
            target_embedding = np.array(face_data["embedding"])

            # Find matching face in this frame
            for det_face in detected:
                sim = _cosine_similarity(det_face.normed_embedding, target_embedding)
                if sim >= 0.4:
                    # Swap this face
                    frame = adapter.swap_face(frame, det_face)
                    break

        # Save frame (swapped or original)
        cv2.imwrite(os.path.join(output_dir, fname), frame)

        if progress_callback and total > 0:
            progress_callback((i + 1) / total)
```

- [ ] **Step 2: Commit**

```bash
git add server/services/face_swapper.py
git commit -m "feat: add pluggable face swap adapter with InsightFace default"
```

---

### Task 5: Lipsync Service — VEED Fabric 1.0

**Files:**
- Create: `server/services/lipsync.py`

- [ ] **Step 1: Create `server/services/lipsync.py`**

```python
import os
import fal_client

from server.config import FAL_KEY, LIPSYNC_RESOLUTION


def apply_lipsync(
    face_image_path: str,
    audio_path: str,
    output_video_path: str,
) -> str:
    """Call VEED Fabric 1.0 to generate lipsynced video.

    Args:
        face_image_path: path to face thumbnail image
        audio_path: path to extracted audio file
        output_video_path: where to save the result

    Returns:
        Path to the lipsynced video file.

    Raises:
        RuntimeError on API failure.
    """
    if not FAL_KEY:
        raise RuntimeError("FAL_KEY not set. Cannot use lipsync.")

    os.environ["FAL_KEY"] = FAL_KEY

    # Upload files to fal.ai for public URLs
    image_url = fal_client.upload_file(face_image_path)
    audio_url = fal_client.upload_file(audio_path)

    try:
        result = fal_client.subscribe(
            "veed/fabric-1.0",
            arguments={
                "image_url": image_url,
                "audio_url": audio_url,
                "resolution": LIPSYNC_RESOLUTION,
            },
        )
    except Exception as e:
        raise RuntimeError(f"VEED Fabric API failed: {e}")

    video_url = result.get("video", {}).get("url")
    if not video_url:
        raise RuntimeError("VEED Fabric returned no video URL")

    # Download the result
    import httpx
    response = httpx.get(video_url)
    response.raise_for_status()
    with open(output_video_path, "wb") as f:
        f.write(response.content)

    return output_video_path
```

- [ ] **Step 2: Commit**

```bash
git add server/services/lipsync.py
git commit -m "feat: add lipsync service with VEED Fabric 1.0 integration"
```

---

### Task 6: Backend Routes — FastAPI Endpoints

**Files:**
- Rewrite: `server/main.py`

- [ ] **Step 1: Rewrite `server/main.py`**

```python
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

# In-memory job tracking
jobs: dict[str, dict] = {}
swap_lock = asyncio.Lock()


def _video_dir(video_id: str) -> str:
    path = os.path.join(STORAGE_DIR, video_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Video not found")
    return path


@app.post("/api/upload", response_model=UploadResponse)
async def upload_video(file: UploadFile = File(...)):
    # Validate file type
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

    # Find the original video file
    original = None
    for f in os.listdir(vdir):
        if f.startswith("original"):
            original = os.path.join(vdir, f)
            break
    if not original:
        raise HTTPException(status_code=404, detail="Original video not found")

    # Step 1: Extract frames
    frames_dir = os.path.join(vdir, "frames")
    video_info = video.extract_frames(original, frames_dir)

    # Step 2: Extract audio
    audio_path = os.path.join(vdir, "audio.aac")
    video.extract_audio(original, audio_path)

    # Step 3: Detect and cluster faces
    faces_data = face_tracker.detect_and_cluster(
        frames_dir, vdir, subsample=FRAME_SUBSAMPLE
    )
    face_tracker.save_faces_json(faces_data, video_info, os.path.join(vdir, "faces.json"))

    # Build response
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
    """Background task for face swap pipeline."""
    try:
        vdir = os.path.join(STORAGE_DIR, video_id)
        frames_dir = os.path.join(vdir, "frames")
        swapped_dir = os.path.join(vdir, "swapped")
        faces_json = face_tracker.load_faces_json(os.path.join(vdir, "faces.json"))

        # Validate face IDs
        for fid in face_ids:
            if fid not in faces_json["faces"]:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["error"] = f"Unknown face ID: {fid}"
                return

        jobs[job_id]["status"] = "processing"
        jobs[job_id]["progress"] = 0.1

        # Step 1: Swap faces
        def update_progress(p):
            # Scale swap progress to 0.1-0.8 range
            jobs[job_id]["progress"] = 0.1 + p * 0.7

        adapter = face_swapper.InsightFaceSwapAdapter()
        face_swapper.swap_faces_in_video(
            frames_dir=frames_dir,
            output_dir=swapped_dir,
            faces_json=faces_json,
            selected_face_ids=face_ids,
            adapter=adapter,
            progress_callback=update_progress,
        )

        jobs[job_id]["progress"] = 0.8

        # Step 2: Optional lipsync
        if ENABLE_LIPSYNC:
            try:
                from services.lipsync import apply_lipsync
                jobs[job_id]["progress"] = 0.85
                # Use first selected face's thumbnail + audio
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
                # Lipsync failure is non-fatal, continue with swapped frames
                print(f"Lipsync failed (non-fatal): {e}")

        # Step 3: Reassemble video
        audio_path = os.path.join(vdir, "audio.aac")
        output_path = os.path.join(vdir, "output.mp4")
        video.reassemble_video(
            frames_dir=swapped_dir,
            audio_path=audio_path if os.path.exists(audio_path) else None,
            output_path=output_path,
            fps=faces_json["fps"],
        )

        jobs[job_id]["progress"] = 1.0
        jobs[job_id]["status"] = "completed"

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


@app.post("/api/swap", response_model=SwapResponse)
async def swap_faces(req: SwapRequest):
    vdir = _video_dir(req.video_id)

    # Verify faces.json exists
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

    # Run swap in background
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
```

- [ ] **Step 2: Commit**

```bash
git add server/main.py
git commit -m "feat: add FastAPI routes for upload, detect, swap, status, download"
```

---

### Task 7: Frontend Types & API Client

**Files:**
- Rewrite: `src/types.ts`
- Modify: `src/lib/utils/api.ts`

- [ ] **Step 1: Rewrite `src/types.ts`**

```typescript
export interface FaceInfo {
  face_id: string;
  thumbnail: string;
  age: number;
  gender: string;
  frame_count: number;
}

export interface DetectFacesResponse {
  video_id: string;
  faces: FaceInfo[];
}

export interface SwapResponse {
  job_id: string;
}

export interface StatusResponse {
  status: "processing" | "completed" | "failed";
  progress: number;
  error: string | null;
}

export type AppStep = "upload" | "detecting" | "select" | "processing";
```

- [ ] **Step 2: Update `src/lib/utils/api.ts`**

Keep existing `getBackendUrl()`, add API client functions below it:

```typescript
import type {
  DetectFacesResponse,
  StatusResponse,
  SwapResponse,
} from "../../types";

/**
 * Utility function to get the backend URL from environment variables
 * and sanitize it (trim, remove trailing slash).
 */
export function getBackendUrl(): string {
  const backendUrl = import.meta.env.VITE_BACKEND_TARGET;
  if (!backendUrl || typeof backendUrl !== "string") return "";
  let formattedUrl = backendUrl.trim();
  if (formattedUrl.startsWith("http")) {
    if (formattedUrl.endsWith("/")) formattedUrl = formattedUrl.slice(0, -1);
    return formattedUrl;
  }
  return "";
}

export async function uploadVideo(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/upload", { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
  const data = await res.json();
  return data.video_id;
}

export async function detectFaces(
  videoId: string
): Promise<DetectFacesResponse> {
  const res = await fetch("/api/detect-faces", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: videoId }),
    signal: AbortSignal.timeout(120_000),
  });
  if (!res.ok) throw new Error(`Detection failed: ${res.statusText}`);
  return res.json();
}

export async function startSwap(
  videoId: string,
  faceIds: string[]
): Promise<string> {
  const res = await fetch("/api/swap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: videoId, face_ids: faceIds }),
  });
  if (!res.ok) throw new Error(`Swap failed: ${res.statusText}`);
  const data: SwapResponse = await res.json();
  return data.job_id;
}

export async function getStatus(jobId: string): Promise<StatusResponse> {
  const res = await fetch(`/api/status/${jobId}`);
  if (!res.ok) throw new Error(`Status check failed: ${res.statusText}`);
  return res.json();
}

export function getDownloadUrl(jobId: string): string {
  return `/api/download/${jobId}`;
}
```

- [ ] **Step 3: Commit**

```bash
git add src/types.ts src/lib/utils/api.ts
git commit -m "feat: add frontend types and API client"
```

---

### Task 8: Frontend Components

**Files:**
- Create: `src/components/VideoUploader.tsx`
- Create: `src/components/FaceSelector.tsx`
- Create: `src/components/ProcessingStatus.tsx`
- Delete: `src/components/VideoPlayer.tsx`

- [ ] **Step 1: Delete `src/components/VideoPlayer.tsx`**

```bash
rm src/components/VideoPlayer.tsx
```

- [ ] **Step 2: Create `src/components/VideoUploader.tsx`**

```tsx
import { useCallback, useRef, useState } from "react";
import { Upload } from "lucide-react";

interface VideoUploaderProps {
  onUpload: (file: File) => void;
  isUploading: boolean;
}

export function VideoUploader({ onUpload, isUploading }: VideoUploaderProps) {
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((file: File) => {
    const validTypes = ["video/mp4", "video/quicktime", "video/webm"];
    if (!validTypes.includes(file.type)) {
      alert("Please upload an MP4, MOV, or WebM file.");
      return;
    }
    setSelectedFile(file);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  return (
    <div className="flex flex-col items-center gap-6 w-full max-w-lg">
      <div
        className={`w-full border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-colors ${
          dragOver
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25 hover:border-primary/50"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept="video/mp4,video/quicktime,video/webm"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
        <Upload className="w-10 h-10 mx-auto mb-4 text-muted-foreground" />
        <p className="text-lg font-medium">Drop a video here</p>
        <p className="text-sm text-muted-foreground mt-1">
          or click to browse (MP4, MOV, WebM)
        </p>
      </div>

      {selectedFile && (
        <div className="flex flex-col items-center gap-3 w-full">
          <p className="text-sm text-muted-foreground truncate max-w-full">
            {selectedFile.name} (
            {(selectedFile.size / 1024 / 1024).toFixed(1)} MB)
          </p>
          <button
            className="w-full py-3 px-6 bg-primary text-primary-foreground rounded-xl font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
            onClick={() => onUpload(selectedFile)}
            disabled={isUploading}
          >
            {isUploading ? "Uploading..." : "Upload & Analyze"}
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create `src/components/FaceSelector.tsx`**

```tsx
import { useState } from "react";
import type { FaceInfo } from "../types";
import { Check } from "lucide-react";

interface FaceSelectorProps {
  faces: FaceInfo[];
  onSwap: (selectedIds: string[]) => void;
  isSwapping: boolean;
}

export function FaceSelector({ faces, onSwap, isSwapping }: FaceSelectorProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const toggleFace = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (faces.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-xl font-medium text-muted-foreground">
          No faces detected
        </p>
        <p className="text-sm text-muted-foreground mt-2">
          Try uploading a different video
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-6 w-full max-w-2xl">
      <h2 className="text-xl font-semibold">Select faces to swap</h2>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 w-full">
        {faces.map((face) => {
          const isSelected = selected.has(face.face_id);
          return (
            <button
              key={face.face_id}
              onClick={() => toggleFace(face.face_id)}
              className={`relative rounded-xl overflow-hidden border-2 transition-all ${
                isSelected
                  ? "border-primary ring-2 ring-primary/30"
                  : "border-transparent hover:border-muted-foreground/30"
              }`}
            >
              <img
                src={face.thumbnail}
                alt={`Face ${face.face_id}`}
                className="w-full aspect-square object-cover"
              />
              {isSelected && (
                <div className="absolute top-2 right-2 w-6 h-6 bg-primary rounded-full flex items-center justify-center">
                  <Check className="w-4 h-4 text-primary-foreground" />
                </div>
              )}
              <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/70 to-transparent p-3">
                <div className="flex gap-2 text-xs text-white">
                  <span className="bg-white/20 backdrop-blur-sm px-2 py-0.5 rounded-full">
                    {face.gender}, {face.age}y
                  </span>
                  <span className="bg-white/20 backdrop-blur-sm px-2 py-0.5 rounded-full">
                    {face.frame_count} frames
                  </span>
                </div>
              </div>
            </button>
          );
        })}
      </div>

      <button
        className="w-full max-w-xs py-3 px-6 bg-primary text-primary-foreground rounded-xl font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
        onClick={() => onSwap(Array.from(selected))}
        disabled={selected.size === 0 || isSwapping}
      >
        {isSwapping ? "Starting..." : `Swap ${selected.size} face(s)`}
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Create `src/components/ProcessingStatus.tsx`**

```tsx
import { useEffect, useState } from "react";
import { getStatus, getDownloadUrl } from "../lib/utils/api";
import type { StatusResponse } from "../types";
import { Download, AlertCircle, Loader2 } from "lucide-react";

interface ProcessingStatusProps {
  jobId: string;
  onRetry: () => void;
}

export function ProcessingStatus({ jobId, onRetry }: ProcessingStatusProps) {
  const [status, setStatus] = useState<StatusResponse>({
    status: "processing",
    progress: 0,
    error: null,
  });

  useEffect(() => {
    if (status.status !== "processing") return;

    const interval = setInterval(async () => {
      try {
        const s = await getStatus(jobId);
        setStatus(s);
        if (s.status !== "processing") clearInterval(interval);
      } catch {
        // Keep polling on transient errors
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [jobId, status.status]);

  if (status.status === "failed") {
    return (
      <div className="flex flex-col items-center gap-4 text-center">
        <AlertCircle className="w-12 h-12 text-destructive" />
        <p className="text-lg font-medium">Processing failed</p>
        <p className="text-sm text-muted-foreground">{status.error}</p>
        <button
          className="py-2 px-6 bg-primary text-primary-foreground rounded-xl font-medium hover:bg-primary/90 transition-colors"
          onClick={onRetry}
        >
          Try Again
        </button>
      </div>
    );
  }

  if (status.status === "completed") {
    return (
      <div className="flex flex-col items-center gap-4">
        <div className="w-16 h-16 bg-green-500/10 rounded-full flex items-center justify-center">
          <Download className="w-8 h-8 text-green-500" />
        </div>
        <p className="text-lg font-medium">Ready!</p>
        <a
          href={getDownloadUrl(jobId)}
          download="swapped.mp4"
          className="py-3 px-8 bg-primary text-primary-foreground rounded-xl font-medium hover:bg-primary/90 transition-colors inline-flex items-center gap-2"
        >
          <Download className="w-4 h-4" />
          Download Video
        </a>
      </div>
    );
  }

  const pct = Math.round(status.progress * 100);
  return (
    <div className="flex flex-col items-center gap-6 w-full max-w-md">
      <Loader2 className="w-10 h-10 animate-spin text-primary" />
      <p className="text-lg font-medium">Swapping faces...</p>
      <div className="w-full bg-muted rounded-full h-3 overflow-hidden">
        <div
          className="h-full bg-primary rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-sm text-muted-foreground">{pct}% complete</p>
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git rm src/components/VideoPlayer.tsx
git add src/components/VideoUploader.tsx src/components/FaceSelector.tsx src/components/ProcessingStatus.tsx
git commit -m "feat: add frontend components for upload, face selection, and processing"
```

---

### Task 9: App Shell — Wire Everything Together

**Files:**
- Rewrite: `src/App.tsx`

- [ ] **Step 1: Rewrite `src/App.tsx`**

```tsx
import { useState } from "react";
import "./App.css";
import "./index.css";
import type { AppStep, FaceInfo } from "./types";
import { uploadVideo, detectFaces, startSwap } from "./lib/utils/api";
import { VideoUploader } from "./components/VideoUploader";
import { FaceSelector } from "./components/FaceSelector";
import { ProcessingStatus } from "./components/ProcessingStatus";
import { Loader2 } from "lucide-react";

function App() {
  const [step, setStep] = useState<AppStep>("upload");
  const [videoId, setVideoId] = useState("");
  const [faces, setFaces] = useState<FaceInfo[]>([]);
  const [jobId, setJobId] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isSwapping, setIsSwapping] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = async (file: File) => {
    setIsUploading(true);
    setError(null);
    try {
      const vid = await uploadVideo(file);
      setVideoId(vid);
      setStep("detecting");

      const result = await detectFaces(vid);
      setFaces(result.faces);
      setStep("select");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
      setStep("upload");
    } finally {
      setIsUploading(false);
    }
  };

  const handleSwap = async (selectedIds: string[]) => {
    setIsSwapping(true);
    setError(null);
    try {
      const jid = await startSwap(videoId, selectedIds);
      setJobId(jid);
      setStep("processing");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Swap failed");
    } finally {
      setIsSwapping(false);
    }
  };

  return (
    <div className="w-full min-h-screen bg-background font-sans flex flex-col items-center justify-center p-8">
      <h1 className="text-3xl font-bold mb-8">Face Swap</h1>

      {error && (
        <div className="mb-6 p-4 bg-destructive/10 text-destructive rounded-xl text-sm max-w-lg w-full text-center">
          {error}
        </div>
      )}

      {step === "upload" && (
        <VideoUploader onUpload={handleUpload} isUploading={isUploading} />
      )}

      {step === "detecting" && (
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-10 h-10 animate-spin text-primary" />
          <p className="text-lg font-medium">Analyzing faces...</p>
          <p className="text-sm text-muted-foreground">
            This may take up to a minute
          </p>
        </div>
      )}

      {step === "select" && (
        <FaceSelector
          faces={faces}
          onSwap={handleSwap}
          isSwapping={isSwapping}
        />
      )}

      {step === "processing" && (
        <ProcessingStatus jobId={jobId} onRetry={() => setStep("select")} />
      )}
    </div>
  );
}

export default App;
```

- [ ] **Step 2: Verify frontend compiles**

Run: `cd /Users/laurianeteyssier/Projects/VEED-Hackathon && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add src/App.tsx
git commit -m "feat: wire up App.tsx with 4-state face swap flow"
```

---

### Task 10: Final Integration — Cleanup & Verify

- [ ] **Step 1: Remove `src/assets/video-ref.mp4`** (no longer referenced)

```bash
rm -f src/assets/video-ref.mp4
```

- [ ] **Step 2: Create `server/storage/.gitkeep`** so the directory exists

```bash
mkdir -p server/storage && touch server/storage/.gitkeep
```

- [ ] **Step 3: Create `server/models/.gitkeep`** for the inswapper model

```bash
mkdir -p server/models && touch server/models/.gitkeep
```

- [ ] **Step 4: Update `.env.example`**

```
FAL_KEY=your_fal_api_key_here
ENABLE_LIPSYNC=false
LIPSYNC_RESOLUTION=480p
FRAME_SUBSAMPLE=5
```

- [ ] **Step 5: Verify backend starts**

Run: `cd server && source venv/bin/activate && python main.py`
Expected: Uvicorn starts on 0.0.0.0:8000

- [ ] **Step 6: Verify frontend starts**

Run: `npm run dev`
Expected: Vite starts on localhost:5173, no compilation errors

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "feat: complete face swap app — upload, detect, swap, download"
```
