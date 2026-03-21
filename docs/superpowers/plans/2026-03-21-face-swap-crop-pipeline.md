# Face Swap Crop-and-Composite Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor face swap to crop per-face video clips, swap each independently in parallel, and composite back into the original frames.

**Architecture:** Instead of swapping faces in-place on full frames, the pipeline: (1) re-detects each selected face on all frames using embedding matching, (2) crops a large stable square region around each face into separate per-face frame sequences, (3) runs `inswapper_128` on each face's frames in parallel threads, (4) composites the swapped crops back onto the original frames at the recorded positions.

**Tech Stack:** Python, OpenCV, InsightFace (`inswapper_128`, `buffalo_l`), NumPy, `concurrent.futures.ThreadPoolExecutor`, FFmpeg

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `server/services/face_swapper.py` | **Rewrite** | New pipeline: crop → parallel swap → composite. Keep adapter classes unchanged. |
| `server/services/video.py` | **Add function** | `assemble_clip()` — create .mp4 from a directory of frame images |
| `server/main.py` | **Minor update** | `_run_swap_job` calls new pipeline function (same signature, drop-in) |

No new files. No schema changes. No frontend changes.

---

### Task 1: Add `assemble_clip` to `video.py`

**Files:**
- Modify: `server/services/video.py`

- [ ] **Step 1: Add `assemble_clip` function**

Add after `reassemble_video`:

```python
def assemble_clip(frames_dir: str, output_path: str, fps: float, frame_pattern: str = "frame_%04d.jpg") -> None:
    """Assemble frame images into a video clip (no audio)."""
    cmd = [
        "ffmpeg", "-framerate", str(fps),
        "-i", os.path.join(frames_dir, frame_pattern),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", output_path, "-y"
    ]
    subprocess.run(cmd, capture_output=True, check=True)
```

- [ ] **Step 2: Verify no syntax errors**

Run: `cd /Users/laurianeteyssier/Projects/VEED-Hackathon && server/venv/bin/python -c "from services import video; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add server/services/video.py
git commit -m "feat: add assemble_clip helper to video service"
```

---

### Task 2: Rewrite `face_swapper.py` — crop logic

**Files:**
- Modify: `server/services/face_swapper.py`

- [ ] **Step 1: Add `_compute_square_crop` helper**

This computes a square crop region centered on a face bbox, with padding. Returns `(x1, y1, x2, y2)` clamped to frame bounds.

```python
def _compute_square_crop(bbox: list[float], frame_shape: tuple, padding_factor: float = 1.5) -> tuple[int, int, int, int]:
    """Compute a padded square crop region centered on a face bbox.

    Args:
        bbox: [x1, y1, x2, y2] face bounding box
        frame_shape: (height, width, channels) of the frame
        padding_factor: multiplier on face size for crop region (1.5 = 50% padding)

    Returns:
        (crop_x1, crop_y1, crop_x2, crop_y2) clamped to frame bounds
    """
    fx1, fy1, fx2, fy2 = bbox
    face_w = fx2 - fx1
    face_h = fy2 - fy1
    face_size = max(face_w, face_h)
    crop_size = int(face_size * padding_factor)

    cx = (fx1 + fx2) / 2
    cy = (fy1 + fy2) / 2

    h, w = frame_shape[:2]
    half = crop_size / 2

    x1 = int(max(0, cx - half))
    y1 = int(max(0, cy - half))
    x2 = int(min(w, cx + half))
    y2 = int(min(h, cy + half))

    return x1, y1, x2, y2
```

- [ ] **Step 2: Add `_detect_face_in_frame` helper**

Finds a specific face in a frame by embedding similarity. Returns the InsightFace face object or None.

```python
def _detect_face_in_frame(frame: np.ndarray, target_embedding: np.ndarray, threshold: float = 0.4):
    """Detect a specific face in a frame by matching embedding.

    Returns the InsightFace face object if found, else None.
    """
    app = _get_app()
    detected = app.get(frame)
    for face in detected:
        sim = _cosine_similarity(face.normed_embedding, target_embedding)
        if sim >= threshold:
            return face
    return None
```

- [ ] **Step 3: Add `crop_face_clips` function**

This is the first phase of the pipeline. For each selected face: re-detect on all frames, crop a square region, save cropped frames to a per-face directory, record crop coordinates in a manifest.

```python
def crop_face_clips(
    frames_dir: str,
    faces_json: dict,
    selected_face_ids: list[str],
    output_base_dir: str,
    progress_callback=None,
) -> dict[str, dict]:
    """Extract per-face cropped frame sequences from the full frames.

    For each selected face:
    1. Re-detect the face on every frame using embedding matching
    2. Crop a padded square region around the face
    3. Save cropped frames to {output_base_dir}/{face_id}/frame_XXXX.jpg

    Returns a manifest dict:
    {
        "face_0": {
            "crop_dir": "/path/to/face_0/",
            "crops": {
                "frame_0001.jpg": (x1, y1, x2, y2),  # crop coords in original frame
                "frame_0005.jpg": (x1, y1, x2, y2),
            },
            "crop_size": (width, height),  # consistent size for all crops of this face
        }
    }
    """
    frame_files = sorted(
        f for f in os.listdir(frames_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    )
    total = len(frame_files)
    manifests = {}

    for face_id in selected_face_ids:
        face_data = faces_json["faces"][face_id]
        target_embedding = np.array(face_data["embedding"])

        clip_dir = os.path.join(output_base_dir, face_id)
        os.makedirs(clip_dir, exist_ok=True)

        # First pass: detect face in all frames, collect bboxes
        per_frame_faces = {}  # fname -> (face_obj, bbox)
        for fname in frame_files:
            frame = cv2.imread(os.path.join(frames_dir, fname))
            if frame is None:
                continue
            face_obj = _detect_face_in_frame(frame, target_embedding)
            if face_obj is not None:
                per_frame_faces[fname] = (face_obj, face_obj.bbox.tolist())

        if not per_frame_faces:
            continue

        # Compute consistent crop size from the largest face bbox across all frames
        all_bboxes = [bbox for _, bbox in per_frame_faces.values()]
        max_face_size = max(
            max(b[2] - b[0], b[3] - b[1]) for b in all_bboxes
        )
        crop_size = int(max_face_size * 1.5)

        # Second pass: crop each frame at a square region centered on the face
        crops_manifest = {}
        for fname, (face_obj, bbox) in per_frame_faces.items():
            frame = cv2.imread(os.path.join(frames_dir, fname))
            h, w = frame.shape[:2]

            cx = (bbox[0] + bbox[2]) / 2
            cy = (bbox[1] + bbox[3]) / 2
            half = crop_size / 2

            x1 = int(max(0, cx - half))
            y1 = int(max(0, cy - half))
            x2 = int(min(w, x1 + crop_size))
            y2 = int(min(h, y1 + crop_size))
            # Adjust start if crop was clamped at the end
            x1 = int(max(0, x2 - crop_size))
            y1 = int(max(0, y2 - crop_size))

            crop = frame[y1:y2, x1:x2]
            cv2.imwrite(os.path.join(clip_dir, fname), crop)
            crops_manifest[fname] = (x1, y1, x2, y2)

        manifests[face_id] = {
            "crop_dir": clip_dir,
            "crops": crops_manifest,
            "crop_size": (crop_size, crop_size),
        }

    if progress_callback:
        progress_callback(1.0)

    return manifests
```

- [ ] **Step 4: Verify no syntax errors**

Run: `cd /Users/laurianeteyssier/Projects/VEED-Hackathon && server/venv/bin/python -c "from services import face_swapper; print('OK')"`

- [ ] **Step 5: Commit**

```bash
git add server/services/face_swapper.py
git commit -m "feat: add crop_face_clips for per-face clip extraction"
```

---

### Task 3: Rewrite `face_swapper.py` — per-clip swap and composite

**Files:**
- Modify: `server/services/face_swapper.py`

- [ ] **Step 1: Add `swap_single_face_clip` function**

Runs the swap on one face's cropped frame sequence. Operates only on the cropped images.

```python
def swap_single_face_clip(
    clip_dir: str,
    output_dir: str,
    target_embedding: np.ndarray,
    adapter: FaceSwapAdapter,
    progress_callback=None,
) -> None:
    """Run face swap on a single face's cropped clip frames.

    Reads cropped frames from clip_dir, detects the face in each crop,
    swaps it, and writes the result to output_dir with the same filenames.
    """
    os.makedirs(output_dir, exist_ok=True)
    app = _get_app()

    frame_files = sorted(
        f for f in os.listdir(clip_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    )
    total = len(frame_files)

    for i, fname in enumerate(frame_files):
        crop = cv2.imread(os.path.join(clip_dir, fname))
        if crop is None:
            continue

        detected = app.get(crop)
        for det_face in detected:
            sim = _cosine_similarity(det_face.normed_embedding, target_embedding)
            if sim >= 0.4:
                crop = adapter.swap_face(crop, det_face)
                break

        cv2.imwrite(os.path.join(output_dir, fname), crop)

        if progress_callback and total > 0:
            progress_callback((i + 1) / total)
```

- [ ] **Step 2: Add `composite_swapped_faces` function**

Pastes swapped crop regions back onto the original frames.

```python
def composite_swapped_faces(
    frames_dir: str,
    output_dir: str,
    manifests: dict[str, dict],
    swapped_base_dir: str,
) -> None:
    """Composite swapped face crops back onto original frames.

    For each frame, copies the original, then pastes each face's swapped crop
    at the recorded position.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Collect all frame filenames that appear in any manifest
    all_frame_files = set()
    for face_id, manifest in manifests.items():
        all_frame_files.update(manifest["crops"].keys())

    # Also include frames with no face (they pass through unchanged)
    for f in os.listdir(frames_dir):
        if f.startswith("frame_") and f.endswith(".jpg"):
            all_frame_files.add(f)

    for fname in sorted(all_frame_files):
        frame = cv2.imread(os.path.join(frames_dir, fname))
        if frame is None:
            continue

        for face_id, manifest in manifests.items():
            if fname not in manifest["crops"]:
                continue

            swapped_crop_path = os.path.join(swapped_base_dir, face_id, fname)
            if not os.path.exists(swapped_crop_path):
                continue

            swapped_crop = cv2.imread(swapped_crop_path)
            if swapped_crop is None:
                continue

            x1, y1, x2, y2 = manifest["crops"][fname]
            crop_h, crop_w = swapped_crop.shape[:2]
            # Ensure dimensions match (handle edge clamping)
            region_h = y2 - y1
            region_w = x2 - x1
            if crop_h != region_h or crop_w != region_w:
                swapped_crop = cv2.resize(swapped_crop, (region_w, region_h))

            frame[y1:y2, x1:x2] = swapped_crop

        cv2.imwrite(os.path.join(output_dir, fname), frame)
```

- [ ] **Step 3: Add `swap_faces_pipeline` — the orchestrator**

Replaces the old `swap_faces_in_video`. Orchestrates: crop → parallel swap → composite.

```python
from concurrent.futures import ThreadPoolExecutor

def swap_faces_pipeline(
    frames_dir: str,
    output_dir: str,
    faces_json: dict,
    selected_face_ids: list[str],
    adapter: FaceSwapAdapter | None = None,
    progress_callback=None,
) -> None:
    """Full face swap pipeline: crop per-face clips → swap in parallel → composite.

    Drop-in replacement for the old swap_faces_in_video.
    Same signature for compatibility with main.py.
    """
    if adapter is None:
        adapter = InsightFaceSwapAdapter()

    base_dir = os.path.dirname(frames_dir)  # e.g., server/storage/{video_id}
    clips_dir = os.path.join(base_dir, "face_clips")
    swapped_clips_dir = os.path.join(base_dir, "swapped_clips")

    # Phase 1: Crop per-face clips
    if progress_callback:
        progress_callback(0.0)

    manifests = crop_face_clips(
        frames_dir, faces_json, selected_face_ids, clips_dir
    )

    if progress_callback:
        progress_callback(0.2)

    if not manifests:
        # No faces detected in any frame — copy originals through
        import shutil
        os.makedirs(output_dir, exist_ok=True)
        for f in os.listdir(frames_dir):
            if f.startswith("frame_") and f.endswith(".jpg"):
                shutil.copy2(os.path.join(frames_dir, f), os.path.join(output_dir, f))
        if progress_callback:
            progress_callback(1.0)
        return

    # Phase 2: Swap each face clip in parallel
    face_ids_to_process = list(manifests.keys())
    completed = [0]
    total_faces = len(face_ids_to_process)

    def face_progress(face_idx):
        def callback(p):
            overall = 0.2 + 0.6 * (face_idx + p) / total_faces
            if progress_callback:
                progress_callback(overall)
        return callback

    def swap_one_face(args):
        face_id, idx = args
        face_data = faces_json["faces"][face_id]
        target_embedding = np.array(face_data["embedding"])
        clip_dir = manifests[face_id]["crop_dir"]
        swap_out = os.path.join(swapped_clips_dir, face_id)
        swap_single_face_clip(
            clip_dir, swap_out, target_embedding, adapter, face_progress(idx)
        )

    with ThreadPoolExecutor(max_workers=min(total_faces, 4)) as executor:
        executor.map(swap_one_face, [(fid, i) for i, fid in enumerate(face_ids_to_process)])

    if progress_callback:
        progress_callback(0.8)

    # Phase 3: Composite swapped faces back onto original frames
    composite_swapped_faces(frames_dir, output_dir, manifests, swapped_clips_dir)

    if progress_callback:
        progress_callback(1.0)
```

- [ ] **Step 4: Remove old `swap_faces_in_video` function**

Delete the old `swap_faces_in_video` function (lines 72-117 of the current file). It is fully replaced by `swap_faces_pipeline`.

- [ ] **Step 5: Verify no syntax errors**

Run: `cd /Users/laurianeteyssier/Projects/VEED-Hackathon && server/venv/bin/python -c "from services import face_swapper; print('OK')"`

- [ ] **Step 6: Commit**

```bash
git add server/services/face_swapper.py
git commit -m "feat: add parallel per-face swap pipeline with crop and composite"
```

---

### Task 4: Update `main.py` to use new pipeline

**Files:**
- Modify: `server/main.py`

- [ ] **Step 1: Update `_run_swap_job` to call `swap_faces_pipeline`**

In `_run_swap_job`, change the call from `face_swapper.swap_faces_in_video` to `face_swapper.swap_faces_pipeline`. The function signature is the same, so this is a one-line change:

```python
# OLD (line 121-128):
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

# NEW:
await asyncio.get_event_loop().run_in_executor(
    None,
    face_swapper.swap_faces_pipeline,
    frames_dir,
    swapped_dir,
    faces_json,
    face_ids,
    adapter,
    update_progress,
)
```

- [ ] **Step 2: Verify no syntax errors**

Run: `cd /Users/laurianeteyssier/Projects/VEED-Hackathon && server/venv/bin/python -c "from main import app; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add server/main.py
git commit -m "feat: wire up crop-and-composite swap pipeline in main"
```

---

### Task 5: Manual smoke test

- [ ] **Step 1: Start the backend**

Run: `cd /Users/laurianeteyssier/Projects/VEED-Hackathon && npm run server`

- [ ] **Step 2: Upload a test video via the frontend or curl**

```bash
curl -X POST http://localhost:8000/api/upload \
  -F "file=@path/to/test_video.mp4"
```

- [ ] **Step 3: Run detect-faces**

```bash
curl -X POST http://localhost:8000/api/detect-faces \
  -H "Content-Type: application/json" \
  -d '{"video_id": "<VIDEO_ID>"}'
```

- [ ] **Step 4: Run swap and verify the output**

```bash
curl -X POST http://localhost:8000/api/swap \
  -H "Content-Type: application/json" \
  -d '{"video_id": "<VIDEO_ID>", "face_ids": ["face_0"]}'
```

Verify:
- `server/storage/{video_id}/face_clips/face_0/` contains cropped frames
- `server/storage/{video_id}/swapped_clips/face_0/` contains swapped crops
- `server/storage/{video_id}/swapped/` contains final composited frames
- `server/storage/{video_id}/output.mp4` plays correctly with swapped face
