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
| Face Swap      | Pluggable adapter (default: InsightFace inswapper)           |
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
