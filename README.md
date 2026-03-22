`git clone --recurse-submodules https://github.com/tonyyunyang/VEED-Hackathon.git && cd VEED-Hackathon`

# VEED Face Swap

VEED Face Swap is a local full-stack app for:

- uploading a short video
- detecting and clustering faces across frames
- selecting tracked faces to replace
- running a face-swap job
- optionally applying lipsync
- downloading the rendered result

This README is written for other developers who need to deploy the project locally without conda. The supported local workflow documented here is:

- `npm` for the frontend
- `uv` for the backend environment and the `npm run server` wrapper
- no `conda`

## Quick Start

If you want the shortest path to a working local setup:

1. Clone the repo with submodules:

   ```bash
   git clone --recurse-submodules https://github.com/tonyyunyang/VEED-Hackathon.git
   cd VEED-Hackathon
   git submodule sync --recursive
   git submodule update --init --recursive
   ```

2. Install system prerequisites:

   - Node.js `20.19+` or `22.12+`
   - npm `10+`
   - Python `3.11` or `3.12`
   - `uv`
   - `ffmpeg`
   - `ffprobe`
   - `curl`

3. Install backend dependencies:

   ```bash
   UV_CACHE_DIR=.uv-cache uv sync --directory server --locked --all-groups
   ```

4. Install frontend dependencies:

   ```bash
   npm install
   ```

5. Create your local env file:

   ```bash
   cp .env.example .env
   ```

6. Add a reference identity source to `.env`:

   ```dotenv
   FACE_SWAP_REFERENCE_IMAGE=/absolute/path/to/source-face.jpg
   ```

   Or populate:

   ```text
   server/reference_faces/
   ```

7. Start all services:

   ```bash
   npm start
   ```

   This launches the backend, FaceFusion API, and frontend together in one terminal with color-coded logs.

8. Open the app:

   - frontend: `http://localhost:5173`
   - backend: `http://localhost:8000`
   - backend docs: `http://localhost:8000/docs`
   - FaceFusion API docs: `http://localhost:8001/docs`

## Clone And Submodules

The app depends on Git submodules. Do not skip them.

Top-level submodules:

- `face-detect-track`
- `facefusion-VEED`

Nested submodules inside `face-detect-track`:

- `BoT-FaceSORT-VEED`
- `insightface-VEED`

Because the root `.gitmodules` file uses HTTPS URLs, a standard recursive clone is enough:

```bash
git clone --recurse-submodules https://github.com/tonyyunyang/VEED-Hackathon.git
cd VEED-Hackathon
```

If you already cloned without submodules:

```bash
git submodule sync --recursive
git submodule update --init --recursive
```

If you want `git pull` to recurse into submodules automatically on your machine:

```bash
git config --global submodule.recurse true
```

## What Is In This Repo

| Path | Purpose |
| --- | --- |
| `src/` | React 19 + TypeScript + Vite frontend |
| `server/` | FastAPI backend |
| `face-detect-track/` | Repo-local face detection and tracking package |
| `facefusion-VEED/` | Optional FaceFusion checkout used by the `facefusion` backend |
| `tests/` | Python API, tracker, swapper, schema, and video-service tests |

Required for a normal local deployment:

- `face-detect-track/`
- `face-detect-track/BoT-FaceSORT-VEED/`
- `face-detect-track/insightface-VEED/`

Optional:

- `facefusion-VEED/` only matters when `FACE_SWAPPER_BACKEND=facefusion`

## Prerequisites

Use these versions for the least surprising local setup:

- Node.js `20.19+` or `22.12+`
- npm `10+`
- Python `3.11` or `3.12`
- `uv`
- `ffmpeg`
- `ffprobe`
- `curl`

Why:

- `server/pyproject.toml` requires Python `>=3.11,<3.13`
- `face-detect-track/pyproject.toml` also requires Python `>=3.11,<3.13`
- Vite `7.3.1` requires Node `^20.19.0 || >=22.12.0`
- the FaceFusion CLI checks for both `ffmpeg` and `curl`

Version checks:

```bash
node --version
npm --version
python3 --version
uv --version
ffmpeg -version
ffprobe -version
curl --version
```

Verified locally in this repo with:

- Node `20.20.1`
- npm `10.8.2`
- Python `3.11.7`
- `uv 0.10.12`

Example `ffmpeg` install commands:

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt-get update
sudo apt-get install -y ffmpeg curl
```

## Install Dependencies

### 1. Backend

From the repo root:

```bash
UV_CACHE_DIR=.uv-cache uv sync --directory server --locked --all-groups
```

What this does:

- creates or updates `server/.venv`
- installs the backend dependencies from `server/pyproject.toml`
- installs `movie-like-shots` from `face-detect-track/` as a local editable dependency
- uses `server/uv.lock`
- keeps the `uv` cache in `.uv-cache/` under the repo root

If you prefer the default global `uv` cache location, omit `UV_CACHE_DIR=.uv-cache`.

### 2. Frontend

From the repo root:

```bash
npm install
```

Use `npm install`, not `npm ci`.

Reason:

- the repo contains `package.json`
- the repo does not contain a committed `package-lock.json`
- the documented workflow here is `npm install` plus `npm run ...`

## Environment Configuration

Create your local env file:

```bash
cp .env.example .env
```

The backend loads the repo-root `.env` automatically.

### Current Default `.env.example`

The checked-in `.env.example` now defaults to:

```dotenv
FACE_SWAPPER_BACKEND=facefusion
FACEFUSION_DIR=facefusion-VEED
ENABLE_LIPSYNC=false
```

That is the easiest first-run local setup in this checkout.

### Variables Most Users Need To Understand

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `FACE_SWAPPER_BACKEND` | No, but important | `facefusion` | Selects the swap backend |
| `FACEFUSION_DIR` | For `facefusion` | `facefusion-VEED` | Path to the checked-out FaceFusion repo |
| `FACEFUSION_PYTHON` | Optional | current Python interpreter | Overrides the Python executable used to launch FaceFusion |
| `RUNWARE_API_KEY` | Recommended | empty | Runware API key for AI face generation (img2img) |
| `FACE_SWAP_REFERENCE_IMAGE` | Optional | empty | Uses one fixed source identity image |
| `FACE_SWAP_REFERENCE_FACES_DIR` | Optional alternative | `server/reference_faces` | Uses a local library of source faces |
| `FACE_SWAP_ALLOW_TARGET_THUMBNAIL_FALLBACK` | Optional | `true` | Reuses the tracked face thumbnail if no source image is available |
| `ENABLE_LIPSYNC` | Optional | `false` | Enables fal.ai lipsync |
| `FAL_KEY` | Only if `ENABLE_LIPSYNC=true` | empty | API key for lipsync |
| `VITE_BACKEND_TARGET` | Optional | `http://localhost:8000` | Changes the frontend proxy target |
| `STORAGE_DIR` | Optional | `server/storage` | Moves uploaded videos and generated outputs elsewhere |

The tracker defaults in `.env.example` are already aligned with the local `movie_like_shots` pipeline and usually do not need to change.

## Reference Face Resolution

The backend resolves a source identity for each detected face using this priority chain. The first match wins:

1. **User-uploaded reference** — uploaded via `POST /api/upload-reference/{video_id}` (per-video, highest priority)
2. **Global env image** — `FACE_SWAP_REFERENCE_IMAGE=/absolute/path/to/source-face.jpg`
3. **Runware AI generation** — if `RUNWARE_API_KEY` is set, generates a neutral face via img2img from the detected face thumbnail. Accepts an optional `style_prompt` on the swap request (e.g. `"wearing sunglasses"`, `"with face paint"`)
4. **Reference library** — deterministic pick from `server/reference_faces/`, matched by gender and age range
5. **Thumbnail fallback** — reuses the tracked face's own thumbnail (when `FACE_SWAP_ALLOW_TARGET_THUMBNAIL_FALLBACK=true`)

### Uploading a per-video reference image

```bash
curl -s -F "file=@face.jpg" http://localhost:8000/api/upload-reference/<VIDEO_ID>
```

Accepts `.jpg`, `.jpeg`, `.png`, `.webp`. Overwrites any previous upload for that video.

### Runware AI generation

Set `RUNWARE_API_KEY` in `.env`. The backend sends the detected face thumbnail as a seed image to Runware with a prompt like:

> Photorealistic front-facing passport-style portrait of a 25-year-old male person, very neutral usual face, neutral expression, plain white background, even studio lighting

The optional `style_prompt` field on `/api/swap` appends user descriptions to the prompt (e.g. `"wearing sunglasses and face paint"`). Input is sanitized: max 200 characters, non-alphanumeric characters stripped, prompt injection patterns blocked.

### Reference library

Put images under:

```text
server/reference_faces/
  male/
  female/
```

If filenames include age ranges like `20-29_name.jpg`, the backend picks an age-matched source image.

### Thumbnail fallback

If nothing else is available, the tracked face's own thumbnail is used when:

```dotenv
FACE_SWAP_ALLOW_TARGET_THUMBNAIL_FALLBACK=true
```

Useful for smoke tests, not for real identity replacement.

## Choose A Swap Backend

The API surface stays the same either way:

- `POST /api/upload`
- `POST /api/upload-reference/{video_id}`
- `POST /api/detect-faces`
- `POST /api/swap`
- `GET /api/status/{job_id}`
- `GET /api/download/{job_id}`

The difference is what happens inside `/api/swap`.

### Option A: `facefusion`

This is the default local path for this repo.

Set:

```dotenv
FACE_SWAPPER_BACKEND=facefusion
FACEFUSION_DIR=facefusion-VEED
```

Notes:

- the repository already includes the `facefusion-VEED` checkout
- the server calls `facefusion.py headless-run` directly
- the checkout already includes local model assets under `facefusion-VEED/.assets/models/`
- FaceFusion uses the same Python interpreter that starts the backend unless you set `FACEFUSION_PYTHON`
- FaceFusion still needs a usable reference image or reference-face library

### Option B: `insightface`

You can still use the legacy InsightFace swap path:

```dotenv
FACE_SWAPPER_BACKEND=insightface
```

Important caveat: the repository does not include `server/models/inswapper_128.onnx`. The InsightFace swap path will fail at swap time until that model file exists at:

```text
server/models/inswapper_128.onnx
```

So for `FACE_SWAPPER_BACKEND=insightface` you need both:

1. a reference face source
2. `server/models/inswapper_128.onnx`

## First-Run Behavior And External Assets

There are two first-run details worth knowing.

### 1. Tracker detector weights

`movie-like-shots` will automatically download the SCRFD detector file into:

```text
face-detect-track/models/scrfd/scrfd_10g_gnkps.onnx
```

if it is missing on the first detection run.

That means:

- the first face-detection request may take longer
- internet access may be required the first time detection is run on a fresh checkout

### 2. FaceFusion assets

This checkout already contains a populated `facefusion-VEED/.assets/models/` directory with the models used by the default local FaceFusion configuration in this repo.

If you change FaceFusion model settings later, FaceFusion may still request additional downloads depending on the processors you enable.

## Run The App

### All services at once (recommended)

```bash
npm start
```

This single command launches all three services with color-coded, prefixed logs:

| Service | Label | URL |
| --- | --- | --- |
| Backend (FastAPI) | `[server]` | `http://localhost:8000` |
| FaceFusion API | `[facefusion]` | `http://localhost:8001` |
| Frontend (Vite) | `[frontend]` | `http://localhost:5173` |

Press `Ctrl+C` to stop all services at once. If the FaceFusion virtualenv is not found, that service is skipped with a warning.

### Running services individually

If you prefer separate terminals:

#### Terminal 1: backend

```bash
npm run server
```

#### Terminal 2: FaceFusion API

```bash
cd facefusion-VEED && .venv/bin/python api.py
```

#### Terminal 3: frontend

```bash
npm run dev -- --host 127.0.0.1
```

### Notes

The Vite dev server proxies `/api` requests to `http://localhost:8000` unless you override `VITE_BACKEND_TARGET`.

If port `8000` is already in use, start the backend directly on another port:

```bash
cd server
UV_CACHE_DIR=../.uv-cache uv run uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

Then start the frontend with:

```bash
VITE_BACKEND_TARGET=http://127.0.0.1:8001 npm run dev -- --host 127.0.0.1
```

## API Smoke Test

You can verify the backend before using the UI.

### 1. Confirm the server is responding

This should return a `404` JSON payload because the job ID does not exist yet:

```bash
curl -i http://127.0.0.1:8000/api/status/nonexist
```

Expected status:

```text
HTTP/1.1 404 Not Found
{"detail":"Job not found"}
```

### 2. Upload a local test video

The repo already includes `tests/fixtures/test_video.mp4`:

```bash
curl -s \
  -F "file=@tests/fixtures/test_video.mp4" \
  http://127.0.0.1:8000/api/upload
```

### 3. Run face detection

Replace `<VIDEO_ID>` with the value from the upload step:

```bash
curl -s \
  -X POST http://127.0.0.1:8000/api/detect-faces \
  -H "Content-Type: application/json" \
  -d '{"video_id":"<VIDEO_ID>"}'
```

### 4. Start a swap job

This only succeeds if you have configured:

- a working swap backend
- a usable reference face source

```bash
curl -s \
  -X POST http://127.0.0.1:8000/api/swap \
  -H "Content-Type: application/json" \
  -d '{"video_id":"<VIDEO_ID>","face_ids":["face_0"]}'
```

### 5. Poll job status

```bash
curl -s http://127.0.0.1:8000/api/status/<JOB_ID>
```

### 6. Download the completed output

```bash
curl -L http://127.0.0.1:8000/api/download/<JOB_ID> --output swapped.mp4
```

## What Gets Written At Runtime

By default, the backend writes working files under:

```text
server/storage/
```

Typical files and folders:

```text
server/storage/<video_id>/
  original.mp4
  frames/
  audio.aac
  faces.json
  swapped/
  output.mp4
```

If `FACE_SWAPPER_BACKEND=facefusion`, temporary runtime folders are also created under:

```text
server/storage/<video_id>/.facefusion_runtime/
```

Those are cleaned up automatically unless:

```dotenv
FACEFUSION_KEEP_INTERMEDIATES=true
```

## Verification Checklist

These are the fastest reliable checks for a new developer after setup.

### Frontend

```bash
npm install
npm run build
```

`npm run build` was verified successfully in this repo.

### Backend startup

```bash
curl -I http://127.0.0.1:8000/docs
```

You should get `HTTP/1.1 200 OK` once the backend is running.

### Full backend test suite

```bash
UV_CACHE_DIR=.uv-cache uv run --directory server pytest ../tests -q
```

### Targeted backend tests

```bash
UV_CACHE_DIR=.uv-cache uv run --directory server pytest ../tests/test_api.py ../tests/test_face_tracker.py ../tests/test_face_swapper.py ../tests/test_schemas.py ../tests/test_video_service.py -q
```

The FFmpeg-backed video-service tests are skipped automatically when `ffmpeg` or `ffprobe` are missing.

## Known Local Gotchas

### `npm run server` fails with `uv: command not found`

Install `uv`, then rerun:

```bash
UV_CACHE_DIR=.uv-cache uv sync --directory server --all-groups
```

### Port `8000` is already in use

Start the backend on another port and point Vite at it:

```bash
cd server
UV_CACHE_DIR=../.uv-cache uv run uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

```bash
VITE_BACKEND_TARGET=http://127.0.0.1:8001 npm run dev -- --host 127.0.0.1
```

### Swap jobs fail immediately

Check the following first:

- `FACE_SWAPPER_BACKEND` is set to the backend you actually want
- you configured `FACE_SWAP_REFERENCE_IMAGE` or added files under `server/reference_faces/`
- if using `insightface`, `server/models/inswapper_128.onnx` exists
- if using `facefusion`, `FACEFUSION_DIR=facefusion-VEED` is correct

### Lipsync fails

Lipsync is optional. If you enable it, you must set:

```dotenv
ENABLE_LIPSYNC=true
FAL_KEY=...
```

### `npm run lint` reports errors from `.venv`, `server/.venv`, `.uv-cache`, or other local caches

That command is not currently the best deployment smoke test in a workspace that already contains local environments or cache directories. Use `npm run build` plus the backend startup/tests above as the reliable setup verification path.

## Architecture Summary

| Layer | What is used |
| --- | --- |
| Frontend | React 19 + TypeScript + Vite + Tailwind CSS 4 |
| Backend API | FastAPI + Uvicorn |
| Face tracking | `movie-like-shots` from the local `face-detect-track` submodule |
| Tracker vendor repos | `BoT-FaceSORT-VEED` and `insightface-VEED` |
| Swap backends | `insightface` or the local `facefusion-VEED` checkout |
| Optional lipsync | fal.ai via `FAL_KEY` |
| Video I/O | `ffmpeg` / `ffprobe` |

## Additional Context

Detailed implementation notes live in:

- `docs/superpowers/specs/2026-03-21-face-swap-design.md`
- `docs/superpowers/plans/2026-03-21-face-swap-implementation.md`
