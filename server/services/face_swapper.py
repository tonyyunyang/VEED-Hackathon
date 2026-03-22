from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
import shutil
import subprocess
import threading
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import cv2
import numpy as np

from config import (
    FACEFUSION_BYPASS_CONTENT_ANALYSER,
    FACEFUSION_DIR,
    FACEFUSION_ENABLE_ENHANCER,
    FACEFUSION_EXECUTION_PROVIDER,
    FACEFUSION_KEEP_INTERMEDIATES,
    FACEFUSION_OUTPUT_VIDEO_QUALITY,
    FACEFUSION_PIXEL_BOOST,
    FACEFUSION_PYTHON,
    FACEFUSION_SWAP_MODEL,
    FACEFUSION_THREAD_COUNT,
    FACE_SWAP_ALLOW_TARGET_THUMBNAIL_FALLBACK,
    FACE_SWAP_REFERENCE_FACES_DIR,
    FACE_SWAP_REFERENCE_IMAGE,
    FACE_SWAPPER_BACKEND,
    RUNWARE_API_KEY,
)
from services import video as video_service

if TYPE_CHECKING:
    from insightface.app import FaceAnalysis

_app: FaceAnalysis | None = None
_swapper = None
_onnx_lock = threading.Lock()

ProgressCallback = Callable[[float], None] | None
StatusCallback = Callable[[dict[str, Any]], None] | None
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

logger = logging.getLogger(__name__)


_STYLE_PROMPT_MAX_LENGTH = 200
_STYLE_PROMPT_BLOCKED_PATTERNS = re.compile(
    r"(ignore\s+(previous|above|all)|system\s*prompt|you\s+are\s+now|"
    r"disregard|forget\s+(everything|instructions)|override|<\s*script|"
    r"javascript\s*:|data\s*:)",
    re.IGNORECASE,
)


def _sanitize_style_prompt(raw: str) -> str:
    """Sanitize user-provided style additions for prompt injection safety."""
    text = raw.strip()
    if not text:
        return ""
    text = re.sub(r"[^\w\s,.\-'/()&]+", "", text)
    if _STYLE_PROMPT_BLOCKED_PATTERNS.search(text):
        logger.warning("Blocked suspicious style prompt: %s", text[:80])
        return ""
    return text[:_STYLE_PROMPT_MAX_LENGTH]


def _build_runware_prompt(age: int, gender: str, style_prompt: str = "") -> str:
    age_desc = f"{age}-year-old " if age > 0 else ""
    gender_desc = f"{gender} " if gender else ""
    base = (
        f"Photorealistic front-facing passport-style portrait of a {age_desc}"
        f"{gender_desc}person, very neutral usual face, "
        "neutral expression, plain white background, even studio lighting"
    )
    sanitized = _sanitize_style_prompt(style_prompt)
    if sanitized:
        base += f", {sanitized}"
    return base


def _generate_face_runware(
    thumbnail_path: str,
    output_path: str,
    age: int,
    gender: str,
    style_prompt: str = "",
) -> str | None:
    """Generate a neutral replacement face via Runware img2img.

    Uses the detected face thumbnail as seed image and steers the generation
    toward a neutral, demographically-consistent face.  Calls the Runware
    WebSocket API directly (no SDK needed).  Returns the path to the
    generated image on success, or ``None`` on failure.
    """
    if not RUNWARE_API_KEY:
        logger.info("Runware: skipping — RUNWARE_API_KEY not set")
        return None

    try:
        import json

        import httpx
        import websockets.sync.client as ws_sync

        RUNWARE_WS_URL = "wss://ws-api.runware.ai/v1"

        prompt = _build_runware_prompt(age, gender, style_prompt)
        logger.info("Runware: generating face (age=%s, gender=%s, style=%r)", age, gender, style_prompt)
        logger.info("Runware: prompt → %s", prompt)

        task_uuid = str(uuid.uuid4())

        with ws_sync.connect(RUNWARE_WS_URL, max_size=None, open_timeout=15) as conn:
            # Authenticate
            conn.send(json.dumps([{"taskType": "authentication", "apiKey": RUNWARE_API_KEY}]))
            auth_resp = json.loads(conn.recv(timeout=15))
            if isinstance(auth_resp, dict) and auth_resp.get("error"):
                logger.warning("Runware auth failed: %s", auth_resp)
                return None
            if isinstance(auth_resp, list):
                for item in auth_resp:
                    if isinstance(item, dict) and item.get("error"):
                        logger.warning("Runware auth failed: %s", item)
                        return None

            logger.info("Runware auth OK, sending text-to-image inference request")

            # Send text-to-image request (no seed — thumbnails are too low
            # quality for img2img; the prompt carries the demographics)
            request_payload = {
                "taskType": "imageInference",
                "taskUUID": task_uuid,
                "model": "runware:101@1",
                "positivePrompt": prompt,
                "width": 512,
                "height": 512,
                "steps": 30,
                "numberResults": 1,
                "outputType": "URL",
                "outputFormat": "JPG",
            }
            conn.send(json.dumps([request_payload]))

            # Wait for result (poll messages until we get our task back)
            image_url = None
            for attempt in range(30):
                raw = conn.recv(timeout=120)
                msg = json.loads(raw)
                logger.debug("Runware recv #%d: %s", attempt, str(msg)[:500])

                # Handle both {"data": [...]} wrapper and raw list formats
                if isinstance(msg, dict):
                    if msg.get("error") or msg.get("errors"):
                        logger.warning("Runware error response: %s", msg)
                        return None
                    data_list = msg.get("data", [])
                elif isinstance(msg, list):
                    data_list = msg
                else:
                    continue

                if not isinstance(data_list, list):
                    continue

                for item in data_list:
                    if not isinstance(item, dict):
                        continue
                    # Check for task-specific error
                    if item.get("taskUUID") == task_uuid and item.get("error"):
                        logger.warning("Runware task error: %s", item)
                        return None
                    # Check for global errors (e.g. invalid request)
                    if item.get("errorId") or item.get("errorMessage"):
                        logger.warning("Runware error: %s", item)
                        return None
                    # Check for our result
                    if item.get("taskUUID") == task_uuid and item.get("imageURL"):
                        image_url = item["imageURL"]
                        break
                if image_url:
                    break

        if not image_url:
            logger.warning("Runware: no image URL received after polling")
            return None

        logger.info("Runware: received image URL → %s", image_url)

        # Download the generated image
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client() as client:
            resp = client.get(image_url)
            resp.raise_for_status()
            with open(output_path, "wb") as out:
                out.write(resp.content)

        logger.info("Runware: generated face saved to %s (%d bytes)", output_path, len(resp.content))
        return output_path

    except Exception:
        logger.warning("Runware face generation failed, falling back", exc_info=True)
        return None


def _get_app() -> FaceAnalysis:
    global _app
    if _app is None:
        from insightface.app import FaceAnalysis

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


def _parse_progress(line: str) -> float | None:
    match = re.search(r"(\d+)%\|", line)
    if match:
        return int(match.group(1)) / 100.0
    return None


def _emit_progress(progress_callback: ProgressCallback, value: float) -> None:
    if progress_callback:
        progress_callback(min(max(value, 0.0), 1.0))


def _emit_status(status_callback: StatusCallback, **payload: Any) -> None:
    if status_callback:
        status_callback(payload)


def _trim_ansi(value: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", value)


def _sorted_frame_files(directory: str) -> list[str]:
    return sorted(
        file_name
        for file_name in os.listdir(directory)
        if file_name.startswith("frame_") and file_name.endswith(".jpg")
    )


def _image_candidates(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def _parse_age_range(path: Path) -> tuple[int, int] | None:
    stem = path.stem.lower()
    match = re.search(r"(?<!\d)(\d{1,3})[-_](\d{1,3})(?!\d)", stem)
    if match:
        start = int(match.group(1))
        end = int(match.group(2))
        return min(start, end), max(start, end)

    exact_match = re.search(r"age[-_]?(\d{1,3})(?!\d)", stem)
    if exact_match:
        age = int(exact_match.group(1))
        return age, age
    return None


def _deterministic_pick(candidates: list[Path], key: str) -> Path | None:
    if not candidates:
        return None
    digest = hashlib.sha1(key.encode("utf-8")).digest()
    index = int.from_bytes(digest[:4], "big") % len(candidates)
    return candidates[index]


def _copy_clip_frames_to_sequence(clip_dir: str, sequence_dir: str) -> list[str]:
    os.makedirs(sequence_dir, exist_ok=True)
    original_names = _sorted_frame_files(clip_dir)
    for index, original_name in enumerate(original_names, start=1):
        source_path = os.path.join(clip_dir, original_name)
        target_path = os.path.join(sequence_dir, f"frame_{index:04d}.jpg")
        shutil.copy2(source_path, target_path)
    return original_names


def _restore_output_frames(
    original_names: list[str],
    sequence_output_dir: str,
    original_clip_dir: str,
    output_dir: str,
) -> None:
    os.makedirs(output_dir, exist_ok=True)
    for index, original_name in enumerate(original_names, start=1):
        generated_path = os.path.join(sequence_output_dir, f"frame_{index:04d}.jpg")
        fallback_path = os.path.join(original_clip_dir, original_name)
        chosen_path = generated_path if os.path.exists(generated_path) else fallback_path
        shutil.copy2(chosen_path, os.path.join(output_dir, original_name))


class ReferenceFaceResolver:
    def __init__(
        self,
        reference_image: str = FACE_SWAP_REFERENCE_IMAGE,
        reference_faces_dir: str = FACE_SWAP_REFERENCE_FACES_DIR,
        allow_target_thumbnail_fallback: bool = FACE_SWAP_ALLOW_TARGET_THUMBNAIL_FALLBACK,
        style_prompt: str = "",
    ):
        self.reference_image = reference_image
        self.reference_faces_dir = reference_faces_dir
        self.allow_target_thumbnail_fallback = allow_target_thumbnail_fallback
        self.style_prompt = style_prompt

    def resolve(self, video_dir: str, face_id: str, face_data: dict) -> str | None:
        logger.info(
            "[%s] Resolving reference face (age=%s, gender=%s, style=%r)",
            face_id, face_data.get("age"), face_data.get("gender"), self.style_prompt,
        )
        # 1. User-uploaded reference image for this video (highest priority)
        uploaded_candidates = sorted(
            name for name in os.listdir(video_dir) if name.startswith("uploaded_reference")
        )
        if uploaded_candidates:
            result = str(Path(video_dir) / uploaded_candidates[0])
            logger.info("[%s] Reference source: user-uploaded image → %s", face_id, result)
            return result

        # 2. Global reference image from env
        direct_path = Path(self.reference_image) if self.reference_image else None
        if direct_path and direct_path.is_file():
            logger.info("[%s] Reference source: global env image → %s", face_id, direct_path)
            return str(direct_path)

        age = int(face_data.get("age") or 0)
        gender = str(face_data.get("gender") or "").strip().lower()

        # 3. Runware AI face generation (text-to-image from demographics)
        thumbnail_name = face_data.get("thumbnail_path")
        if RUNWARE_API_KEY and thumbnail_name:
            thumbnail_path = Path(video_dir) / thumbnail_name
            if thumbnail_path.is_file():
                logger.info("[%s] Attempting Runware AI generation (thumbnail: %s)", face_id, thumbnail_path)
                output_path = str(
                    Path(video_dir) / f".runware_generated_{face_id}.jpg"
                )
                generated = _generate_face_runware(
                    str(thumbnail_path), output_path, age, gender,
                    self.style_prompt,
                )
                if generated:
                    logger.info("[%s] Reference source: Runware AI generated → %s", face_id, generated)
                    return generated
                logger.warning("[%s] Runware generation failed, trying fallbacks", face_id)
            else:
                logger.warning("[%s] Runware: thumbnail not found at %s", face_id, thumbnail_path)
        elif not RUNWARE_API_KEY:
            logger.info("[%s] Runware: skipped (no API key)", face_id)

        # 4. Fallback: pick from local reference library
        candidates = self._candidates_for_face(face_id, gender, age)
        if candidates:
            logger.info("[%s] Reference source: local library → %s", face_id, candidates)
            return str(candidates)

        if self.allow_target_thumbnail_fallback:
            if thumbnail_name:
                thumbnail_path = Path(video_dir) / thumbnail_name
                if thumbnail_path.is_file():
                    logger.info("[%s] Reference source: thumbnail fallback → %s", face_id, thumbnail_path)
                    return str(thumbnail_path)

        logger.warning("[%s] Reference source: none found", face_id)
        return None

    def _candidates_for_face(self, face_id: str, gender: str, age: int) -> Path | None:
        root = Path(self.reference_faces_dir)
        if not root.exists():
            return None

        search_dirs: list[Path] = []
        gender_dir = root / gender if gender else None
        if gender_dir and gender_dir.is_dir():
            search_dirs.append(gender_dir)
        search_dirs.append(root)

        age_matched: list[Path] = []
        all_candidates: list[Path] = []
        seen: set[Path] = set()

        for search_dir in search_dirs:
            for candidate in _image_candidates(search_dir):
                if candidate in seen:
                    continue
                seen.add(candidate)
                all_candidates.append(candidate)
                parsed_age = _parse_age_range(candidate)
                if age > 0 and parsed_age and parsed_age[0] <= age <= parsed_age[1]:
                    age_matched.append(candidate)

        if age_matched:
            return _deterministic_pick(age_matched, face_id)
        return _deterministic_pick(all_candidates, face_id)


class FaceSwapAdapter(ABC):
    @abstractmethod
    def swap_face(self, frame: np.ndarray, target_face, source_face=None) -> np.ndarray:
        raise NotImplementedError


class InsightFaceSwapAdapter(FaceSwapAdapter):
    def __init__(self, reference_image_path: str | None = None):
        self._source_face = None
        if reference_image_path and os.path.exists(reference_image_path):
            self._load_source(reference_image_path)

    def _load_source(self, image_path: str) -> None:
        app = _get_app()
        img = cv2.imread(image_path)
        if img is None:
            return
        faces = app.get(img)
        if faces:
            self._source_face = faces[0]

    def has_source_face(self) -> bool:
        return self._source_face is not None

    def set_source_face(self, face) -> None:
        self._source_face = face

    def swap_face(self, frame: np.ndarray, target_face, source_face=None) -> np.ndarray:
        swapper = _get_swapper()
        src = source_face or self._source_face
        if src is None:
            return frame
        with _onnx_lock:
            return swapper.get(frame, target_face, src, paste_back=True)


class FaceSwapEngine(ABC):
    @abstractmethod
    def swap_clip(
        self,
        *,
        clip_dir: str,
        output_dir: str,
        face_id: str,
        face_data: dict,
        target_embedding: np.ndarray,
        fps: float,
        progress_callback: ProgressCallback = None,
    ) -> None:
        raise NotImplementedError


class InsightFaceSwapEngine(FaceSwapEngine):
    def __init__(
        self,
        video_dir: str,
        reference_resolver: ReferenceFaceResolver | None = None,
    ):
        self.video_dir = video_dir
        self.reference_resolver = reference_resolver or ReferenceFaceResolver()

    def swap_clip(
        self,
        *,
        clip_dir: str,
        output_dir: str,
        face_id: str,
        face_data: dict,
        target_embedding: np.ndarray,
        fps: float,
        progress_callback: ProgressCallback = None,
    ) -> None:
        del fps
        source_path = self.reference_resolver.resolve(self.video_dir, face_id, face_data)
        if not source_path:
            raise RuntimeError(
                f"No reference face image available for {face_id}. "
                "Configure FACE_SWAP_REFERENCE_IMAGE or populate FACE_SWAP_REFERENCE_FACES_DIR."
            )

        adapter = InsightFaceSwapAdapter(source_path)
        if not adapter.has_source_face():
            raise RuntimeError(f"No detectable source face found in reference image: {source_path}")

        swap_single_face_clip(
            clip_dir=clip_dir,
            output_dir=output_dir,
            target_embedding=target_embedding,
            adapter=adapter,
            progress_callback=progress_callback,
        )


class FaceFusionSwapEngine(FaceSwapEngine):
    def __init__(
        self,
        video_dir: str,
        reference_resolver: ReferenceFaceResolver | None = None,
    ):
        self.video_dir = video_dir
        self.reference_resolver = reference_resolver or ReferenceFaceResolver()
        self.facefusion_root = Path(FACEFUSION_DIR)
        self.facefusion_script = self.facefusion_root / "facefusion.py"
        self.bypass_content_analyser = FACEFUSION_BYPASS_CONTENT_ANALYSER

    def _build_swap_cmd(
        self,
        *,
        source_path: str,
        target_path: str,
        output_path: str,
        temp_path: str,
        jobs_path: str,
    ) -> list[str]:
        processors = ["face_swapper"]
        if FACEFUSION_ENABLE_ENHANCER:
            processors.append("face_enhancer")

        return [
            FACEFUSION_PYTHON,
            str(self.facefusion_script),
            "headless-run",
            "--temp-path",
            temp_path,
            "--jobs-path",
            jobs_path,
            "-s",
            source_path,
            "-t",
            target_path,
            "-o",
            output_path,
            "--processors",
            *processors,
            "--execution-providers",
            FACEFUSION_EXECUTION_PROVIDER,
            "--face-selector-mode",
            "one",
            "--face-swapper-model",
            FACEFUSION_SWAP_MODEL,
            "--face-swapper-pixel-boost",
            FACEFUSION_PIXEL_BOOST,
            "--output-video-quality",
            str(FACEFUSION_OUTPUT_VIDEO_QUALITY),
            "--execution-thread-count",
            str(FACEFUSION_THREAD_COUNT),
        ]

    def _collect_job_failure_details(self, jobs_path: Path) -> str | None:
        failed_dir = jobs_path / "failed"
        if not failed_dir.is_dir():
            return None

        failed_jobs = sorted(failed_dir.glob("*.json"), key=lambda path: path.stat().st_mtime)
        if not failed_jobs:
            return None

        latest_job = failed_jobs[-1]
        try:
            raw_json = latest_job.read_text(encoding="utf-8")
        except OSError:
            return None

        return f"FaceFusion job metadata: {latest_job}\n{raw_json}"

    def _run_facefusion_cmd(
        self,
        cmd: list[str],
        *,
        jobs_path: Path,
        progress_callback: ProgressCallback = None,
    ) -> None:
        if not Path(FACEFUSION_PYTHON).exists():
            raise FileNotFoundError(
                f"FaceFusion Python executable not found: {FACEFUSION_PYTHON}"
            )
        if not self.facefusion_script.exists():
            raise FileNotFoundError(
                f"FaceFusion entrypoint not found: {self.facefusion_script}"
            )

        process_env = os.environ.copy()
        if self.bypass_content_analyser:
            process_env["FACEFUSION_BYPASS_CONTENT_ANALYSER"] = "1"

        process = subprocess.Popen(
            cmd,
            cwd=str(self.facefusion_root),
            env=process_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        output_lines: list[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            output_lines.append(_trim_ansi(line).rstrip())
            if len(output_lines) > 50:
                output_lines.pop(0)
            progress = _parse_progress(line)
            if progress is not None:
                _emit_progress(progress_callback, progress)

        return_code = process.wait()
        if return_code != 0:
            tail = "\n".join(output_lines[-20:])
            job_failure_details = self._collect_job_failure_details(jobs_path)
            detail_parts = [part for part in [tail, job_failure_details] if part]
            details = "\n\n".join(detail_parts)
            raise RuntimeError(f"FaceFusion exited with code {return_code}:\n{details}")

    def swap_clip(
        self,
        *,
        clip_dir: str,
        output_dir: str,
        face_id: str,
        face_data: dict,
        target_embedding: np.ndarray,
        fps: float,
        progress_callback: ProgressCallback = None,
    ) -> None:
        del target_embedding

        source_path = self.reference_resolver.resolve(self.video_dir, face_id, face_data)
        if not source_path:
            raise RuntimeError(
                f"No reference face image available for {face_id}. "
                "Configure FACE_SWAP_REFERENCE_IMAGE or populate FACE_SWAP_REFERENCE_FACES_DIR."
            )

        run_root = (
            Path(self.video_dir)
            / ".facefusion_runtime"
            / f"{face_id}-{uuid.uuid4().hex[:8]}"
        )
        input_frames_dir = run_root / "input_frames"
        output_frames_dir = run_root / "output_frames"
        temp_path = run_root / "temp"
        jobs_path = run_root / "jobs"
        input_video_path = run_root / "input.mp4"
        output_video_path = run_root / "output.mp4"

        try:
            original_names = _copy_clip_frames_to_sequence(clip_dir, str(input_frames_dir))
            if not original_names:
                os.makedirs(output_dir, exist_ok=True)
                return

            _emit_progress(progress_callback, 0.05)
            temp_path.mkdir(parents=True, exist_ok=True)
            jobs_path.mkdir(parents=True, exist_ok=True)

            video_service.reassemble_video(
                str(input_frames_dir),
                None,
                str(input_video_path),
                fps,
            )

            _emit_progress(progress_callback, 0.15)
            cmd = self._build_swap_cmd(
                source_path=source_path,
                target_path=str(input_video_path),
                output_path=str(output_video_path),
                temp_path=str(temp_path),
                jobs_path=str(jobs_path),
            )
            self._run_facefusion_cmd(
                cmd,
                jobs_path=jobs_path,
                progress_callback=lambda progress: _emit_progress(
                    progress_callback,
                    0.15 + progress * 0.70,
                ),
            )

            if not output_video_path.exists():
                raise RuntimeError("FaceFusion did not produce an output video")

            _emit_progress(progress_callback, 0.88)
            video_service.extract_frames(str(output_video_path), str(output_frames_dir))
            _emit_progress(progress_callback, 0.94)

            _restore_output_frames(
                original_names=original_names,
                sequence_output_dir=str(output_frames_dir),
                original_clip_dir=clip_dir,
                output_dir=output_dir,
            )
            _emit_progress(progress_callback, 1.0)
        finally:
            if not FACEFUSION_KEEP_INTERMEDIATES and run_root.exists():
                shutil.rmtree(run_root, ignore_errors=True)


def create_swap_engine(
    video_dir: str,
    reference_resolver: ReferenceFaceResolver | None = None,
    style_prompt: str = "",
) -> FaceSwapEngine:
    if reference_resolver is None:
        reference_resolver = ReferenceFaceResolver(style_prompt=style_prompt)
    backend = FACE_SWAPPER_BACKEND.strip().lower()
    if backend == "insightface":
        return InsightFaceSwapEngine(video_dir, reference_resolver)
    if backend == "facefusion":
        return FaceFusionSwapEngine(video_dir, reference_resolver)
    raise ValueError(
        f"Unsupported FACE_SWAPPER_BACKEND={FACE_SWAPPER_BACKEND!r}. "
        "Expected 'insightface' or 'facefusion'."
    )


def swap_single_face_clip(
    clip_dir: str,
    output_dir: str,
    target_embedding: np.ndarray,
    adapter: FaceSwapAdapter,
    progress_callback: ProgressCallback = None,
) -> None:
    os.makedirs(output_dir, exist_ok=True)

    frame_files = _sorted_frame_files(clip_dir)
    total = len(frame_files)

    for index, file_name in enumerate(frame_files):
        crop = cv2.imread(os.path.join(clip_dir, file_name))
        if crop is None:
            continue

        with _onnx_lock:
            detected = _get_app().get(crop)
        for detected_face in detected:
            similarity = _cosine_similarity(detected_face.normed_embedding, target_embedding)
            if similarity >= 0.4:
                crop = adapter.swap_face(crop, detected_face)
                break

        cv2.imwrite(os.path.join(output_dir, file_name), crop)
        if total > 0:
            _emit_progress(progress_callback, (index + 1) / total)


def composite_swapped_faces(
    frames_dir: str,
    output_dir: str,
    manifests: dict[str, dict],
    swapped_base_dir: str,
    frame_names: list[str] | None = None,
    progress_callback: ProgressCallback = None,
) -> None:
    os.makedirs(output_dir, exist_ok=True)

    all_frame_files = sorted(set(frame_names or _sorted_frame_files(frames_dir)))
    total = len(all_frame_files)

    for index, file_name in enumerate(all_frame_files):
        frame = cv2.imread(os.path.join(frames_dir, file_name))
        if frame is None:
            continue

        for face_id, manifest in manifests.items():
            if file_name not in manifest["crops"]:
                continue

            swapped_crop_path = os.path.join(swapped_base_dir, face_id, file_name)
            if not os.path.exists(swapped_crop_path):
                continue

            swapped_crop = cv2.imread(swapped_crop_path)
            if swapped_crop is None:
                continue

            x1, y1, x2, y2 = manifest["crops"][file_name]
            region_h = y2 - y1
            region_w = x2 - x1
            crop_h, crop_w = swapped_crop.shape[:2]
            if crop_h != region_h or crop_w != region_w:
                swapped_crop = cv2.resize(swapped_crop, (region_w, region_h))

            frame[y1:y2, x1:x2] = swapped_crop

        cv2.imwrite(os.path.join(output_dir, file_name), frame)
        if total > 0:
            _emit_progress(progress_callback, (index + 1) / total)


def swap_faces_pipeline(
    manifests: dict[str, dict],
    faces_json: dict,
    frames_dir: str,
    output_dir: str,
    engine: FaceSwapEngine | None = None,
    progress_callback: ProgressCallback = None,
    status_callback: StatusCallback = None,
    frame_names: list[str] | None = None,
) -> None:
    if engine is None:
        engine = create_swap_engine(os.path.dirname(frames_dir))

    base_dir = os.path.dirname(frames_dir)
    swapped_clips_dir = os.path.join(base_dir, "swapped_clips")
    fps = float(faces_json.get("fps", 30.0))
    output_frame_names = sorted(set(frame_names or _sorted_frame_files(frames_dir)))
    total_output_frames = len(output_frame_names)

    _emit_progress(progress_callback, 0.0)

    if not manifests:
        os.makedirs(output_dir, exist_ok=True)
        _emit_status(
            status_callback,
            phase="compositing",
            message=f"Preparing {total_output_frames} frame(s) for output",
            completed_frames=0,
            total_frames=total_output_frames,
        )
        for index, file_name in enumerate(output_frame_names):
            shutil.copy2(os.path.join(frames_dir, file_name), os.path.join(output_dir, file_name))
            if total_output_frames > 0:
                progress = (index + 1) / total_output_frames
                _emit_progress(progress_callback, progress)
                _emit_status(
                    status_callback,
                    phase="compositing",
                    message=f"Preparing {total_output_frames} frame(s) for output",
                    completed_frames=index + 1,
                    total_frames=total_output_frames,
                )
        _emit_progress(progress_callback, 1.0)
        return

    face_ids_to_process = list(manifests.keys())
    total_faces = len(face_ids_to_process)
    total_swap_frames = sum(len(manifests[face_id]["crops"]) for face_id in face_ids_to_process)
    total_work_units = max(1, total_swap_frames + total_output_frames)
    processed_swap_frames = 0

    if total_swap_frames > 0:
        _emit_status(
            status_callback,
            phase="swapping",
            message=f"Swapping {total_faces} face(s) across {total_swap_frames} frame(s)",
            completed_frames=0,
            total_frames=total_swap_frames,
        )

    for face_index, face_id in enumerate(face_ids_to_process, start=1):
        face_data = faces_json["faces"][face_id]
        target_embedding = np.array(face_data["embedding"])
        clip_dir = manifests[face_id]["clip_dir"]
        swap_out = os.path.join(swapped_clips_dir, face_id)
        if os.path.exists(swap_out):
            shutil.rmtree(swap_out)
        face_frame_total = len(manifests[face_id]["crops"])
        last_completed = 0

        def face_progress(progress: float) -> None:
            nonlocal last_completed
            completed_for_face = min(
                face_frame_total,
                max(last_completed, int(round(progress * face_frame_total))),
            )
            last_completed = completed_for_face
            _emit_progress(
                progress_callback,
                (processed_swap_frames + completed_for_face) / total_work_units,
            )
            _emit_status(
                status_callback,
                phase="swapping",
                message=f"Swapping {face_id} ({face_index}/{total_faces})",
                completed_frames=processed_swap_frames + completed_for_face,
                total_frames=total_swap_frames,
            )

        engine.swap_clip(
            clip_dir=clip_dir,
            output_dir=swap_out,
            face_id=face_id,
            face_data=face_data,
            target_embedding=target_embedding,
            fps=fps,
            progress_callback=face_progress,
        )
        processed_swap_frames += face_frame_total

    if total_output_frames > 0:
        _emit_status(
            status_callback,
            phase="compositing",
            message=f"Compositing {total_output_frames} frame(s)",
            completed_frames=0,
            total_frames=total_output_frames,
        )

    def composite_progress(progress: float) -> None:
        completed_frames = min(
            total_output_frames,
            int(round(progress * total_output_frames)),
        )
        _emit_progress(
            progress_callback,
            (processed_swap_frames + completed_frames) / total_work_units,
        )
        _emit_status(
            status_callback,
            phase="compositing",
            message=f"Compositing {total_output_frames} frame(s)",
            completed_frames=completed_frames,
            total_frames=total_output_frames,
        )

    composite_swapped_faces(
        frames_dir,
        output_dir,
        manifests,
        swapped_clips_dir,
        frame_names=output_frame_names,
        progress_callback=composite_progress,
    )
    _emit_progress(progress_callback, 1.0)


if __name__ == "__main__":
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from services import video as video_service
    from services.face_tracker import (
        detect_and_cluster,
        extract_face_clips,
        load_faces_json,
        save_faces_json,
    )

    if len(sys.argv) < 2:
        print("Usage: python -m services.face_swapper <video_path> [output_dir]")
        print("  video_path: path to an .mp4/.mov/.webm video file")
        print("  output_dir: where to write results (default: server/test_swap_output/)")
        sys.exit(1)

    video_path = os.path.abspath(sys.argv[1])
    if not os.path.exists(video_path):
        print(f"Error: video not found: {video_path}")
        sys.exit(1)

    test_dir = (
        sys.argv[2]
        if len(sys.argv) > 2
        else os.path.join(os.path.dirname(__file__), "..", "test_swap_output")
    )
    test_dir = os.path.abspath(test_dir)

    os.makedirs(test_dir, exist_ok=True)
    frames_dir = os.path.join(test_dir, "frames")
    swapped_dir = os.path.join(test_dir, "swapped")
    faces_json_path = os.path.join(test_dir, "faces.json")

    print(f"[1/6] Extracting frames from {video_path}...")
    video_info = video_service.extract_frames(video_path, frames_dir)
    fps = video_info["fps"]
    print(f"       {video_info['total_frames']} frames at {fps} fps")

    audio_path = os.path.join(test_dir, "audio.aac")
    video_service.extract_audio(video_path, audio_path)

    print("[2/6] Detecting faces...")
    faces_data = detect_and_cluster(frames_dir, test_dir, subsample=5)
    save_faces_json(faces_data, video_info, faces_json_path)
    faces_json = load_faces_json(faces_json_path)

    face_ids = list(faces_json["faces"].keys())
    print(f"       Found {len(face_ids)} face(s): {face_ids}")
    if not face_ids:
        print("No faces found. Exiting.")
        sys.exit(1)

    selected = [face_ids[0]]
    print(f"       Swapping: {selected}")

    print("[3/6] Extracting face clips...")
    clips_dir = os.path.join(test_dir, "face_clips")
    manifests = extract_face_clips(frames_dir, faces_json, selected, clips_dir)
    print(f"       Created clips for {list(manifests.keys())}")

    print("[4/6] Swapping faces in clips...")

    def on_progress(progress: float) -> None:
        print(f"       progress: {progress:.0%}", end="\r")

    swap_faces_pipeline(manifests, faces_json, frames_dir, swapped_dir, progress_callback=on_progress)
    print()

    original_out = os.path.join(test_dir, "original_reassembled.mp4")
    print("[5/6] Reassembling original video...")
    video_service.reassemble_video(
        frames_dir,
        audio_path if os.path.exists(audio_path) else None,
        original_out,
        fps,
    )

    swapped_out = os.path.join(test_dir, "swapped_output.mp4")
    print("[6/6] Reassembling swapped video...")
    video_service.reassemble_video(
        swapped_dir,
        audio_path if os.path.exists(audio_path) else None,
        swapped_out,
        fps,
    )

    print()
    print("Done! Output files:")
    print(f"  Original: {original_out}")
    print(f"  Swapped:  {swapped_out}")
