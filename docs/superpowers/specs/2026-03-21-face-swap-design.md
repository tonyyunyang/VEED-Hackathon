# VEED Face Swap — Design Spec

## Overview

A video editing tool that detects faces in short video clips (~10s), lets the user select which faces to replace, swaps them with AI-generated replacement faces (matched by age/gender), and optionally applies lipsync via VEED Fabric 1.0 when the video contains speech. Original audio is preserved.

## Constraints

- **Deadline:** 2026-03-22 (hackathon, 1 day)
- **Team:** 3 people working in parallel
- **Workstreams:** Face tracking & identification / Face replacement / Frontend
- **Video length:** ~10 second clips
- **Storage:** Local filesystem
- **Processing:** Local (may move to server later)

## Tech Stack

| Layer          | Technology                                           |
|----------------|------------------------------------------------------|
| Frontend       | React 19 + TypeScript + Vite + Tailwind 4 + shadcn   |
| Backend        | Python, FastAPI + Uvicorn                             |
| Face Detection | InsightFace (detection, recognition, age/gender)      |
| Face Swap      | Pluggable — behind an adapter interface (swap API TBD)|
| Lipsync        | VEED Fabric 1.0 via fal.ai (optional, config-driven) |
| Video I/O      | FFmpeg (frame extraction, reassembly, audio)          |
| Storage        | Local filesystem (`server/storage/`)                  |

## Existing Codebase

The repo already has a working scaffold. We build on top of it, not from scratch.

### What exists

- **Frontend:** Vite + React 19 + Tailwind 4 + shadcn UI components in `src/`. Has react-router, zustand, lucide-react. Vite proxies `/api` to `http://localhost:8000`.
- **Backend:** `server/main.py` with FastAPI + CORS. Run via `npm run server` (activates `server/venv/`). There's also a root-level `.venv/` managed by uv — use `server/venv/` for backend deps (matches the npm script). Remove template code from `main.py` (Google GenAI imports, json_repair, etc.) and replace with face-swap routes.
- **Existing code to replace:** `src/components/VideoPlayer.tsx` (scene selection player — not needed), `src/types.ts` (Van rental types — leftover from template). These get replaced with face-swap UI and types.

### What we create

- New frontend components in `src/components/`
- New API client functions in `src/lib/utils/api.ts` (file exists with `getBackendUrl()` helper — keep it, add fetch wrappers alongside)
- New backend routes in `server/` (add to existing `main.py` or create router files)
- New backend services in `server/services/`
- `server/storage/` for temp files

## Repo Structure

```
├── server/
│   ├── main.py                  # FastAPI app (existing, extend with routes)
│   ├── requirements.txt         # Python deps (existing, add new deps)
│   ├── config.py                # Backend config (lipsync toggle, API keys)
│   ├── venv/                    # Python virtualenv (existing)
│   ├── services/
│   │   ├── face_tracker.py      # Person 1: detection + clustering + age/gender
│   │   ├── face_swapper.py      # Person 2: pluggable face swap adapter
│   │   ├── lipsync.py           # Person 2: VEED Fabric 1.0 integration
│   │   ├── video.py             # Person 2: FFmpeg frame extraction + reassembly
│   ├── models/
│   │   ├── schemas.py           # Pydantic request/response models
│   ├── storage/                 # Local temp storage (gitignored)
├── src/
│   ├── App.tsx                  # Replace with face-swap flow
│   ├── main.tsx                 # Keep as-is
│   ├── types.ts                 # Replace with face-swap types
│   ├── components/
│   │   ├── VideoUploader.tsx     # Person 3
│   │   ├── FaceSelector.tsx      # Person 3
│   │   ├── ProcessingStatus.tsx  # Person 3
│   │   ├── ui/                   # shadcn components (existing, reuse)
│   ├── lib/
│   │   ├── utils/
│   │   │   ├── api.ts            # API client functions
├── package.json                  # Existing
├── vite.config.ts                # Existing (already proxies /api)
```

### Workstream Boundaries

- **Person 1** owns `server/services/face_tracker.py` — detection, clustering, age/gender
- **Person 2** owns `server/services/face_swapper.py` + `server/services/lipsync.py` + `server/services/video.py` — face swap adapter, VEED Fabric lipsync, FFmpeg
- **Person 3** owns `src/components/` — VideoUploader, FaceSelector, ProcessingStatus, App.tsx
- **Shared contract:** `server/models/schemas.py` + `src/types.ts` + route definitions in `server/main.py` — agree on these first

## Prerequisites & Setup

### System dependencies
```bash
brew install ffmpeg     # macOS
```

### Python dependencies (add to `server/requirements.txt`)
```
insightface>=0.7.3
onnxruntime>=1.17.0
opencv-python>=4.9.0
numpy>=1.26.0
python-multipart>=0.0.9
fal-client>=0.5.0
httpx>=0.28.0
```

### InsightFace models
```bash
# Downloads automatically on first run to ~/.insightface/models/
# buffalo_l: detection + recognition + age/gender (~300MB)
```

### Environment variables (`.env`)
```
FAL_KEY=your_fal_api_key_here
ENABLE_LIPSYNC=false
```

### Frontend (already set up)
```bash
npm install   # already done
npm run dev   # starts Vite on :5173
```

## Backend Configuration (`server/config.py`)

```python
ENABLE_LIPSYNC: bool  # from env var ENABLE_LIPSYNC, default False
FAL_KEY: str          # from env var FAL_KEY
LIPSYNC_RESOLUTION: str  # "480p" or "720p", default "480p"
```

When `ENABLE_LIPSYNC` is `True`, the pipeline adds a lipsync pass after face swap. This is a backend-only toggle — the user has no control over it from the frontend.

## API Contract

All routes prefixed with `/api` to match Vite proxy config.

### `POST /api/upload`

- **Input:** Multipart form with `file` field (video)
- **Output:** `{ "video_id": "string" }`
- **Behavior:** Stores video at `server/storage/{video_id}/original.mp4`
- **Errors:** 400 if file is not a valid video format

### `POST /api/detect-faces`

- **Input:** `{ "video_id": "string" }`
- **Output:**
```json
{
  "video_id": "abc123",
  "faces": [
    {
      "face_id": "face_0",
      "thumbnail": "data:image/jpeg;base64,...",
      "age": 30,
      "gender": "male",
      "frame_count": 142
    }
  ]
}
```
- **Behavior:** Synchronous. Extracts frames (subsampled: every 5th frame to keep detection under ~15s), runs InsightFace detection + clustering, returns unique persons with representative thumbnails.
- **Errors:** 404 if video_id not found. Response with `"faces": []` if no faces detected.
- **Timeout:** Frontend must set a long timeout (120s) and show a spinner.

### `POST /api/swap`

- **Input:** `{ "video_id": "string", "face_ids": ["face_0", "face_2"] }`
- **Output:** `{ "job_id": "string" }`
- **Behavior:** Async. For each selected face_id, the system:
  1. Calls the face swap API to generate a swapped face for each frame
  2. If `ENABLE_LIPSYNC` is true: runs VEED Fabric lipsync pass
  3. Reassembles the final video with original audio
- No user input on replacement appearance (auto-matched by age/gender).
- **Errors:** 400 if face_ids contains unknown IDs. 404 if video_id not found.

### `GET /api/status/{job_id}`

- **Output:** `{ "status": "processing" | "completed" | "failed", "progress": 0.0-1.0, "error": "string | null" }`
- When `status` is `"failed"`, `error` contains a human-readable message. When not failed, `error` is `null`.
- **Errors:** 404 if job_id not found.

### `GET /api/download/{job_id}`

- **Output:** `.mp4` file as streaming response
- **Errors:** 404 if job_id not found or job not completed.

## Shared Data: `faces.json`

Written by Person 1, read by Person 2. Stored at `server/storage/{video_id}/faces.json`.

```json
{
  "fps": 30.0,
  "total_frames": 300,
  "faces": {
    "face_0": {
      "age": 30,
      "gender": "male",
      "thumbnail_path": "face_0_thumb.jpg",
      "embedding": [0.12, -0.34, "...512 floats"],
      "frames": {
        "0": [x1, y1, x2, y2],
        "5": [x1, y1, x2, y2],
        "10": [x1, y1, x2, y2]
      }
    }
  }
}
```

- Bounding boxes use InsightFace native format: `[x1, y1, x2, y2]` (top-left, bottom-right corners)
- `frames` keys are frame indices as strings (JSON limitation). Person 2 must parse them as integers when iterating. During swap, Person 2 re-detects on all frames using the known embedding (more reliable than interpolation).
- `embedding` is the InsightFace face embedding (512-dim float array) — used by Person 2 to identify the same face on non-subsampled frames.

## Face Swap API (Pluggable)

The face swap API is behind an adapter interface so different APIs can be tried.

### Adapter interface (`face_swapper.py`)

```python
class FaceSwapAdapter:
    """Base interface for face swap providers."""

    async def swap_face(
        self,
        source_frame: np.ndarray,      # Original frame (BGR)
        face_bbox: list[float],         # [x1, y1, x2, y2]
        face_embedding: np.ndarray,     # 512-dim embedding of face to replace
        target_age: int,                # Age of replacement face
        target_gender: str,             # "male" or "female"
    ) -> np.ndarray:
        """Return the frame with the face swapped. Same dimensions as input."""
        raise NotImplementedError
```

Person 2 implements concrete adapters (e.g. `InsightFaceSwapAdapter`, or a future API-based adapter). The active adapter is selected via config. For the initial implementation, use InsightFace `inswapper_128` as the default.

### Default adapter: InsightFace inswapper

1. Generate a reference face image (placeholder: use a stock image or AI-generated image per age/gender)
2. Run InsightFace `FaceAnalysis` on the reference to get the source face object
3. Run `inswapper_128`: source = reference face, target = detected face in frame
4. Return the swapped frame

## VEED Fabric 1.0 — Lipsync Integration

### When it runs

Only when `ENABLE_LIPSYNC=true` in backend config. Runs as a post-processing step AFTER face swap, BEFORE final reassembly.

### How it works (`lipsync.py`)

1. After face swap produces swapped frames, reassemble them into a temporary video (no audio)
2. For each swapped face, crop the face region across all frames into a separate "face video"
3. Extract original audio → `server/storage/{video_id}/audio.aac`
4. Call VEED Fabric 1.0 via fal.ai:

```python
import fal_client

result = fal_client.subscribe(
    "veed/fabric-1.0",
    arguments={
        "image_url": "<URL of swapped face thumbnail>",
        "audio_url": "<URL of extracted audio>",
        "resolution": "480p",  # from config
    },
)
# result["video"]["url"] → URL of lipsynced face video
```

5. Download the Fabric output video
6. Composite the lipsynced face region back over the swapped video frames
7. Proceed to final reassembly

### File hosting for Fabric API

Fabric requires public URLs for `image_url` and `audio_url`. Options:
- Use fal.ai's file upload: `fal_client.upload_file()` to get a hosted URL
- Or serve files temporarily from the FastAPI server

### Auth

- **Env var:** `FAL_KEY`
- Set as `FAL_KEY` environment variable (fal-client reads it automatically)

### Error handling

- On Fabric API failure: mark swap job as `"failed"` with error message. No retry.
- Fabric is async (queue-based). Use `fal_client.subscribe()` which handles polling.

## Processing Pipeline

### Step 1: Frame Extraction (`video.py` — Person 2)

- FFmpeg extracts all frames at native FPS → `server/storage/{video_id}/frames/frame_0000.jpg`
- Extracts audio track → `server/storage/{video_id}/audio.aac`
- Records FPS and total frame count

### Step 2: Face Tracking & Identification (`face_tracker.py` — Person 1)

- Load subsampled frames (every 5th), run InsightFace `FaceAnalysis` (model: `buffalo_l`)
- For each detected face: extract 512-dim embedding, bounding box `[x1,y1,x2,y2]`, age, gender
- Cluster embeddings using cosine similarity >= 0.4 (similarity, not distance) to group same-person faces across frames
- Per cluster: pick best thumbnail (largest face, most frontal), compute avg age, majority-vote gender
- Write `faces.json` to storage
- Return face metadata to the API layer

### Step 3: Face Swap (`face_swapper.py` — Person 2)

For each selected `face_id`:
1. Call the active `FaceSwapAdapter.swap_face()` for every frame where that face appears
2. Re-detect faces on all frames (not just subsampled) using the stored embedding to find the target face
3. Write swapped frames to `server/storage/{video_id}/swapped/`

### Step 4: Lipsync (optional — `lipsync.py` — Person 2)

Only runs if `ENABLE_LIPSYNC=true`:
1. Upload swapped face thumbnail + audio to fal.ai
2. Call VEED Fabric 1.0 → get lipsynced face video
3. Composite lipsynced face back over swapped frames
4. Overwrite swapped frames with lipsynced versions

### Step 5: Reassembly (`video.py` — Person 2)

- FFmpeg combines final frames + original audio → `server/storage/{video_id}/output.mp4`
- Preserves original FPS, resolution, audio timing

### Concurrency

- One swap job at a time (simple: use `asyncio.Lock`)
- Job status tracked in-memory dict: `{ job_id: { status, progress, video_id } }`
- No cleanup of old files (out of scope for hackathon)

## Frontend Design

### Replace existing code

- `src/types.ts` → face-swap types (FaceInfo, SwapJob, AppState)
- `src/App.tsx` → linear state machine (no router needed, but keep BrowserRouter for potential future use)
- `src/components/VideoPlayer.tsx` → delete (not needed)

### Single-page app with 4 sequential states

**State 1: Upload** — Drag-and-drop zone using shadcn Card. Accepts `.mp4`, `.mov`, `.webm`. Shows file name after selection. "Upload" button calls `POST /api/upload`.

**State 2: Detecting** — Spinner (shadcn Spinner) with text "Analyzing faces...". Calls `POST /api/detect-faces` immediately. Fetch timeout set to 120s.

**State 3: Select Faces** — Grid of face cards (shadcn Card). Each shows: thumbnail image, age badge, gender badge, frame count. Click toggles selection (border highlight). "Swap Faces" button (disabled until >= 1 selected) calls `POST /api/swap`. If no faces detected, show empty state with "No faces found" message.

**State 4: Processing & Download** — Polls `GET /api/status/{job_id}` every 2s. Shows shadcn Progress bar. On `completed`: "Download" button triggers `GET /api/download/{job_id}` as file download. On `failed`: error message + "Try Again" button resets to State 3.

### State management

- Simple `useState` for the current step and its data
- No zustand needed (linear flow, no shared state across routes)
- Types defined in `src/types.ts`
