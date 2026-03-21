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
| Face Detection | InsightFace (ArcFace for detection, recognition, age/gender) |
| Face Swap      | Pluggable adapter (default: InsightFace inswapper)           |
| Lipsync        | VEED Fabric 1.0 via fal.ai (optional, config-driven)         |
| Video I/O      | FFmpeg                                                       |

## Setup

### Prerequisites

```bash
brew install ffmpeg
```

### Backend

```bash
cd server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Frontend

```bash
npm install
```

### Environment

Copy `.env.example` to `.env` and fill in:

```
FAL_KEY=your_fal_api_key
ENABLE_LIPSYNC=false
```

## Running

```bash
# Terminal 1: backend
npm run server

# Terminal 2: frontend
npm run dev
```

Frontend runs on `http://localhost:5173`, backend on `http://localhost:8000`.

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
