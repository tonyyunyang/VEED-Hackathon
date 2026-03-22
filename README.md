# VEED Face Swap

A video editing tool that detects faces in short clips (~10s), lets users select which faces to replace, swaps them with AI-generated faces matched by age/gender, and optionally applies lipsync via VEED Fabric 1.0. Original audio is preserved.

## How It Works

1. **Upload** a short video clip
2. **Detect** — system identifies and clusters all unique faces across frames
3. **Select** one or more faces to swap
4. **Swap** — system replaces selected faces (with optional lipsync)
5. **Download** the modified video

## Architecture

| Layer          | Technology                                                   |
|----------------|--------------------------------------------------------------|
| Frontend       | React 19 + TypeScript + Vite + Tailwind 4 + shadcn           |
| Backend        | Python, FastAPI + Uvicorn                                    |
| Face Tracking  | `movie-like-shots` via `face-detect-track` submodule         |
| Face Detection | InsightFace (recognition, age/gender enrichment)             |
| Face Swap      | Pluggable backend (`insightface` or repo-local `facefusion-VEED`) |
| Lipsync        | VEED Fabric 1.0 via fal.ai (optional, config-driven)         |
| Video I/O      | FFmpeg                                                       |

## Setup

### Clone

Clone recursively so Git also pulls:
- the `face-detect-track` submodule
- the nested tracker/detector repos inside it

```bash
git clone --recurse-submodules git@github.com:tonyyunyang/VEED-Hackathon.git
cd VEED-Hackathon
```

If you already cloned the repo without submodules:

```bash
git submodule update --init --recursive
```

### Prerequisites

```bash
brew install ffmpeg
```

`ffmpeg` and `ffprobe` must be on your `PATH` for video extraction, reassembly, and the FFmpeg-backed tests.

### Backend

This repo now supports two local backend setup styles:
- `uv` + `server/.venv` for the existing workflow
- `conda` + your own interpreter, which is useful when you want FaceFusion and the server to share one environment

#### Option A: existing `uv` workflow

```bash
cd server
uv sync --all-groups
cd ..
```

Notes:
- conda is optional for local isolation only; the repo does not require conda to run
- if you want `uv` to manage Python for you, run `uv python install 3.11` once before `uv sync`
- if you prefer a local conda env, activate it first and then run `uv sync --python "$(which python)" --all-groups`
- `uv` resolves the local `movie-like-shots` dependency from `face-detect-track/`
- the synced backend environment lives under `server/.venv`
- the default tracker backend is `movie_like_shots` with `ocsort`

#### Option B: shared `conda` env (`veed`)

The repo contains a minimal `environment.yml` plus a bootstrap script that installs the shared backend stack into the active interpreter and verifies the local `facefusion-VEED` checkout in place.

```bash
conda env create -f environment.yml
conda activate veed
./scripts/bootstrap_veed_env.sh
```

`environment.yml` pins Python 3.11 because it is the safest cross-stack option for the tracker backend and the legacy InsightFace swap path. If you already have a `veed` env, skip the create step and just activate it before running the bootstrap script.

The bootstrap script intentionally installs the shared backend dependency set through the local `server` package instead of blindly piping `facefusion-VEED/requirements.txt` into the same interpreter. That keeps one compatible environment for the tracker backend, the existing server, and the new FaceFusion swap runner, while still smoke-checking `facefusion-VEED/facefusion.py headless-run`.

### Frontend

```bash
npm install
```

### Environment

Copy `.env.example` to `.env` and fill in:

```
FAL_KEY=your_fal_api_key
ENABLE_LIPSYNC=false
DUMMY_TRACKING=false
```

The tracker-related defaults in `.env.example` are already set to use the merged `movie_like_shots` pipeline.

### FaceFusion Backend

The server keeps the existing upload/detect/swap/download API contract and can now use `facefusion-VEED` as the swap backend under the hood.

To enable it:

```bash
FACE_SWAPPER_BACKEND=facefusion
FACEFUSION_DIR=facefusion-VEED
```

By default the FaceFusion runner uses the same Python interpreter that started the server. In a conda workflow that means it will use your active `veed` env automatically. If you want to force a specific interpreter, set `FACEFUSION_PYTHON`.

When `FACE_SWAPPER_BACKEND=facefusion`, face metadata enrichment defaults off so the backend does not need to import InsightFace just to compute age/gender/embeddings. You can force it back on with `ENABLE_FACE_METADATA_ENRICHMENT=true` if your local environment supports InsightFace cleanly.

FaceFusion still needs a source identity image. Provide one of:
- `FACE_SWAP_REFERENCE_IMAGE=/absolute/path/to/source-face.jpg`
- a local library under `server/reference_faces/male/` and `server/reference_faces/female/`

If the reference library filenames include age ranges such as `20-29_actor.jpg`, the backend will prefer an age-matched file for the selected tracked face. If no reference image is configured, the server can fall back to the tracked face thumbnail when `FACE_SWAP_ALLOW_TARGET_THUMBNAIL_FALLBACK=true`, which is useful for smoke tests but not for meaningful identity replacement.

## Running

```bash
# Terminal 1: backend
npm run server

# Terminal 2: frontend
npm run dev
```

Frontend runs on `http://localhost:5173`, backend on `http://localhost:8000`.

You can also run the backend directly without the npm wrapper:

```bash
cd server
uv run uvicorn main:app --port 8000
```

The normal runtime path is `uv` + `server/.venv`; there is no repo-level conda requirement.

With a shared conda env, you can also run:

```bash
conda activate veed
cd server
python -m uvicorn main:app --port 8000
```

## Testing

Backend tests:

```bash
server/.venv/bin/pytest tests/test_face_tracker.py tests/test_api.py tests/test_schemas.py
```

Full Python suite:

```bash
server/.venv/bin/pytest tests
```

The FFmpeg-backed video service tests in `tests/test_video_service.py` are skipped automatically when `ffmpeg` or `ffprobe` are not installed.

## Team Workstreams

| Person | Scope | Key Files |
|--------|-------|-----------|
| 1 | Face tracking & identification | `server/services/face_tracker.py` |
| 2 | Face replacement & lipsync | `server/services/face_swapper.py`, `lipsync.py`, `video.py` |
| 3 | Frontend | `src/components/`, `src/App.tsx` |

Shared contract: `server/models/schemas.py` + `src/types.ts`

## API Endpoints

- `POST /api/upload` — upload video
- `POST /api/detect-faces` — detect and cluster faces
- `POST /api/swap` — start async face swap job
- `GET /api/status/{job_id}` — poll job progress
- `GET /api/download/{job_id}` — download result

Full spec: [`docs/superpowers/specs/2026-03-21-face-swap-design.md`](docs/superpowers/specs/2026-03-21-face-swap-design.md)
