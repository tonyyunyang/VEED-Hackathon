from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
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
    FACEFUSION_TIMEOUT_SECONDS,
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
_crop_app: FaceAnalysis | None = None
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
_RUNWARE_API_URL = "https://api.runware.ai/v1"
_RUNWARE_INITIAL_POLL_DELAY_SECONDS = 2.0
_RUNWARE_MAX_POLL_DELAY_SECONDS = 8.0
_RUNWARE_MAX_WAIT_SECONDS = 150.0


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


@dataclass(frozen=True)
class ReferenceResolution:
    path: str | None
    source_label: str | None = None


def _runware_error_message(payload: dict[str, Any], task_uuid: str | None = None) -> str | None:
    errors = payload.get("errors")
    if not isinstance(errors, list):
        return None

    for item in errors:
        if not isinstance(item, dict):
            continue
        if task_uuid and item.get("taskUUID") not in {None, task_uuid}:
            continue
        message = str(item.get("message") or item.get("code") or "Runware task failed")
        code = str(item.get("code") or "").strip()
        if code and code not in message:
            return f"{code}: {message}"
        return message
    return None


def _runware_image_url(payload: dict[str, Any], task_uuid: str) -> tuple[str | None, str]:
    data = payload.get("data")
    if not isinstance(data, list):
        return None, "missing"

    saw_matching_task = False
    for item in data:
        if not isinstance(item, dict) or item.get("taskUUID") != task_uuid:
            continue
        saw_matching_task = True
        status = str(item.get("status") or "").strip().lower()
        if item.get("imageURL"):
            return str(item["imageURL"]), "ready"
        if status in {"queued", "pending", "processing"}:
            return None, "processing"
        if status in {"success", "completed"}:
            return None, "malformed"

    if saw_matching_task:
        return None, "malformed"
    return None, "missing"


def _post_runware_tasks(client: Any, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    response = client.post(_RUNWARE_API_URL, json=tasks)
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Runware returned a non-JSON response") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Runware returned an unexpected response payload")

    if response.status_code >= 400:
        detail = _runware_error_message(payload) or response.text.strip() or f"HTTP {response.status_code}"
        raise RuntimeError(f"Runware HTTP {response.status_code}: {detail}")

    return payload


def _generate_face_runware(
    thumbnail_path: str,
    output_path: str,
    age: int,
    gender: str,
    style_prompt: str = "",
) -> tuple[str | None, str | None]:
    """Generate a neutral replacement face via Runware img2img.

    Uses the detected face thumbnail as seed image and steers the generation
    toward a neutral, demographically-consistent face. Calls Runware's
    documented async image inference flow and polls until the image is ready.
    Returns ``(path, error)`` where ``path`` is the generated image on success
    and ``error`` is a human-readable failure reason on fallback.
    """
    if not RUNWARE_API_KEY:
        logger.info("Runware: skipping — RUNWARE_API_KEY not set")
        return None, "Runware API key is not configured on the server"

    try:
        import httpx

        prompt = _build_runware_prompt(age, gender, style_prompt)
        logger.info("Runware: generating face (age=%s, gender=%s, style=%r)", age, gender, style_prompt)
        logger.info("Runware: prompt → %s", prompt)

        task_uuid = str(uuid.uuid4())
        # Text-to-image only — no seedImage; the prompt carries the demographics
        request_payload = [{
            "taskType": "imageInference",
            "taskUUID": task_uuid,
            "deliveryMethod": "async",
            "model": "runware:101@1",
            "positivePrompt": prompt,
            "width": 512,
            "height": 512,
            "steps": 30,
            "numberResults": 1,
            "outputType": "URL",
            "outputFormat": "JPG",
            "includeCost": True,
        }]

        headers = {
            "Authorization": f"Bearer {RUNWARE_API_KEY}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(connect=15.0, read=30.0, write=30.0, pool=30.0)

        logger.info("Submitting Runware async imageInference task %s", task_uuid)

        with httpx.Client(headers=headers, timeout=timeout) as client:
            submit_payload = _post_runware_tasks(client, request_payload)
            submit_error = _runware_error_message(submit_payload, task_uuid)
            if submit_error:
                logger.warning("Runware submission failed for task %s: %s", task_uuid, submit_error)
                return None, submit_error

            image_url, submit_state = _runware_image_url(submit_payload, task_uuid)
            if submit_state == "malformed":
                return None, "Runware returned a completed response without an image URL"
            poll_delay = _RUNWARE_INITIAL_POLL_DELAY_SECONDS
            deadline = time.monotonic() + _RUNWARE_MAX_WAIT_SECONDS
            missing_poll_count = 0

            while not image_url and time.monotonic() < deadline:
                logger.info(
                    "Polling Runware task %s for completion in %.1fs",
                    task_uuid,
                    poll_delay,
                )
                time.sleep(poll_delay)
                poll_payload = _post_runware_tasks(
                    client,
                    [{"taskType": "getResponse", "taskUUID": task_uuid}],
                )
                poll_error = _runware_error_message(poll_payload, task_uuid)
                if poll_error:
                    logger.warning("Runware task %s failed: %s", task_uuid, poll_error)
                    return None, poll_error
                image_url, poll_state = _runware_image_url(poll_payload, task_uuid)
                if poll_state == "malformed":
                    return None, "Runware returned a completed response without an image URL"
                if poll_state == "missing":
                    missing_poll_count += 1
                    if missing_poll_count >= 3:
                        return None, (
                            "Runware polling returned no data for the submitted task UUID"
                        )
                else:
                    missing_poll_count = 0
                poll_delay = min(poll_delay * 1.5, _RUNWARE_MAX_POLL_DELAY_SECONDS)

            if not image_url:
                logger.warning("Runware task %s timed out after %.1fs", task_uuid, _RUNWARE_MAX_WAIT_SECONDS)
                return None, (
                    "Runware image generation timed out while waiting for async task completion"
                )

            logger.info("Runware task %s completed, downloading generated image", task_uuid)
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            resp = client.get(image_url)
            resp.raise_for_status()
            with open(output_path, "wb") as out:
                out.write(resp.content)

        logger.info("Runware: generated face saved to %s (%d bytes)", output_path, len(resp.content))
        return output_path, None

    except Exception as exc:
        logger.warning("Runware face generation failed, falling back", exc_info=True)
        return None, str(exc)


def _get_app() -> FaceAnalysis:
    global _app
    if _app is None:
        from insightface.app import FaceAnalysis

        _app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        _app.prepare(ctx_id=0, det_size=(640, 640))
    return _app


def _get_crop_app() -> FaceAnalysis:
    """Lightweight detector for pre-cropped face regions (smaller det_size)."""
    global _crop_app
    if _crop_app is None:
        from insightface.app import FaceAnalysis

        _crop_app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        _crop_app.prepare(ctx_id=0, det_size=(256, 256))
    return _crop_app


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
    logger.info("FaceFusion progress: %.2f%%", value * 100)
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
    fallback_count = 0
    for index, original_name in enumerate(original_names, start=1):
        generated_path = os.path.join(sequence_output_dir, f"frame_{index:04d}.jpg")
        fallback_path = os.path.join(original_clip_dir, original_name)
        if os.path.exists(generated_path):
            chosen_path = generated_path
        else:
            chosen_path = fallback_path
            fallback_count += 1
        shutil.copy2(chosen_path, os.path.join(output_dir, original_name))
    if fallback_count > 0:
        logger.warning(
            "_restore_output_frames: %d/%d frames fell back to originals (FaceFusion didn't produce them)",
            fallback_count, len(original_names),
        )


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
        self._warnings: list[str] = []

    def get_warnings(self) -> list[str]:
        return list(self._warnings)

    def _record_warning(self, message: str) -> None:
        if message and message not in self._warnings:
            self._warnings.append(message)

    def _resolve_fallback(self, video_dir: str, face_id: str, face_data: dict) -> ReferenceResolution:
        direct_path = Path(self.reference_image) if self.reference_image else None
        if direct_path and direct_path.is_file():
            return ReferenceResolution(
                path=str(direct_path),
                source_label="the configured server reference image",
            )

        age = int(face_data.get("age") or 0)
        gender = str(face_data.get("gender") or "").strip().lower()
        candidates = self._candidates_for_face(face_id, gender, age)
        if candidates:
            return ReferenceResolution(
                path=str(candidates),
                source_label="the local reference face library",
            )

        thumbnail_name = face_data.get("thumbnail_path")
        if self.allow_target_thumbnail_fallback and thumbnail_name:
            thumbnail_path = Path(video_dir) / thumbnail_name
            if thumbnail_path.is_file():
                return ReferenceResolution(
                    path=str(thumbnail_path),
                    source_label="the detected face thumbnail",
                )

        return ReferenceResolution(path=None, source_label=None)

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

        fallback_resolution = self._resolve_fallback(video_dir, face_id, face_data)
        raw_style_prompt = self.style_prompt.strip()
        sanitized_style_prompt = _sanitize_style_prompt(self.style_prompt)

        if raw_style_prompt and not sanitized_style_prompt:
            if fallback_resolution.path:
                self._record_warning(
                    "Runware reference generation was skipped because the prompt was rejected "
                    f"during sanitization. Falling back to {fallback_resolution.source_label}."
                )
            return fallback_resolution.path

        # 2. Runware AI face generation (text-to-image from demographics) when requested
        thumbnail_name = face_data.get("thumbnail_path")
        if sanitized_style_prompt:
            if not thumbnail_name:
                if fallback_resolution.path:
                    self._record_warning(
                        "Runware reference generation was skipped because no detected face thumbnail "
                        f"was available. Falling back to {fallback_resolution.source_label}."
                    )
                return fallback_resolution.path

            thumbnail_path = Path(video_dir) / thumbnail_name
            if not thumbnail_path.is_file():
                if fallback_resolution.path:
                    self._record_warning(
                        "Runware reference generation was skipped because the detected face thumbnail "
                        f"could not be found. Falling back to {fallback_resolution.source_label}."
                    )
                return fallback_resolution.path

            generated, runware_error = _generate_face_runware(
                str(thumbnail_path),
                str(Path(video_dir) / f".runware_generated_{face_id}.jpg"),
                int(face_data.get("age") or 0),
                str(face_data.get("gender") or "").strip().lower(),
                sanitized_style_prompt,
            )
            if generated:
                return generated

            if runware_error and fallback_resolution.path:
                self._record_warning(
                    f"Runware reference generation failed for {face_id}: {runware_error}. "
                    f"Falling back to {fallback_resolution.source_label}."
                )
            logger.info("[%s] Reference source: fallback → %s", face_id, fallback_resolution.path)
            return fallback_resolution.path

        # 3. No requested generation, so use the configured fallback chain directly
        return fallback_resolution.path

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
    def get_warnings(self) -> list[str]:
        return []

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

    def get_warnings(self) -> list[str]:
        return self.reference_resolver.get_warnings()

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

    def get_warnings(self) -> list[str]:
        return self.reference_resolver.get_warnings()

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

        timeout = FACEFUSION_TIMEOUT_SECONDS
        logger.info("FaceFusion: starting subprocess (timeout=%ds)", timeout)
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
        logger.info("FaceFusion: process exited with code %d", return_code)
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
                logger.info("[%s] swap_clip: no frames to process, skipping", face_id)
                os.makedirs(output_dir, exist_ok=True)
                return

            logger.info(
                "[%s] swap_clip: %d clip frames, assembling input video",
                face_id, len(original_names),
            )
            _emit_progress(progress_callback, 0.05)
            temp_path.mkdir(parents=True, exist_ok=True)
            jobs_path.mkdir(parents=True, exist_ok=True)

            video_service.reassemble_video(
                str(input_frames_dir),
                None,
                str(input_video_path),
                fps,
            )
            logger.info("[%s] swap_clip: input video assembled, launching FaceFusion", face_id)

            _emit_progress(progress_callback, 0.15)
            cmd = self._build_swap_cmd(
                source_path=source_path,
                target_path=str(input_video_path),
                output_path=str(output_video_path),
                temp_path=str(temp_path),
                jobs_path=str(jobs_path),
            )
            logger.info("[%s] swap_clip: FaceFusion cmd: %s", face_id, " ".join(cmd))
            t0 = time.monotonic()
            self._run_facefusion_cmd(
                cmd,
                jobs_path=jobs_path,
                progress_callback=lambda progress: _emit_progress(
                    progress_callback,
                    0.15 + progress * 0.70,
                ),
            )
            elapsed = time.monotonic() - t0
            output_size = output_video_path.stat().st_size if output_video_path.exists() else 0
            input_size = input_video_path.stat().st_size if input_video_path.exists() else 0
            logger.info(
                "[%s] swap_clip: FaceFusion finished in %.1fs — input=%dKB output=%dKB",
                face_id, elapsed, input_size // 1024, output_size // 1024,
            )
            if elapsed < 5.0 and len(original_names) > 10:
                logger.warning(
                    "[%s] swap_clip: FaceFusion finished suspiciously fast (%.1fs for %d frames) "
                    "— it may not have processed properly",
                    face_id, elapsed, len(original_names),
                )

            if not output_video_path.exists():
                raise RuntimeError("FaceFusion did not produce an output video")

            logger.info("[%s] swap_clip: >>> starting extract_frames from FaceFusion output", face_id)
            _emit_progress(progress_callback, 0.88)
            video_service.extract_frames(str(output_video_path), str(output_frames_dir))
            logger.info("[%s] swap_clip: <<< extract_frames done", face_id)

            output_frame_count = len([
                f for f in os.listdir(str(output_frames_dir))
                if f.startswith("frame_") and f.endswith(".jpg")
            ])
            logger.info(
                "[%s] swap_clip: extracted %d output frames (expected %d)",
                face_id, output_frame_count, len(original_names),
            )

            _emit_progress(progress_callback, 0.94)
            _restore_output_frames(
                original_names=original_names,
                sequence_output_dir=str(output_frames_dir),
                original_clip_dir=clip_dir,
                output_dir=output_dir,
            )
            logger.info("[%s] swap_clip: <<< _restore_output_frames done", face_id)
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
    logger.info("swap_single_face_clip: %d frames to process", total)
    swapped_count = 0
    last_log_pct = -1

    for index, file_name in enumerate(frame_files):
        crop = cv2.imread(os.path.join(clip_dir, file_name))
        if crop is None:
            logger.warning("swap_single_face_clip: could not read frame %s", file_name)
            continue

        # Use smaller detector since crops are already isolated to face region.
        # Skip cosine similarity — the crop IS the target face, just pick the
        # largest detected face (most prominent in the pre-cropped region).
        with _onnx_lock:
            detected = _get_crop_app().get(crop)
        if detected:
            best_face = max(
                detected,
                key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
            )
            crop = adapter.swap_face(crop, best_face)
            swapped_count += 1

        cv2.imwrite(os.path.join(output_dir, file_name), crop)
        if total > 0:
            pct = int((index + 1) / total * 100)
            if pct >= last_log_pct + 10:
                logger.info("swap_single_face_clip: %d/%d frames (%.0f%%), %d swapped", index + 1, total, pct, swapped_count)
                last_log_pct = pct
            _emit_progress(progress_callback, (index + 1) / total)

    logger.info("swap_single_face_clip: done — %d/%d frames had face swapped", swapped_count, total)


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
    logger.info("composite_swapped_faces: %d frames to composite", total)
    last_log_pct = -1

    for index, file_name in enumerate(all_frame_files):
        # Skip loading frames that have no swapped crops — just copy original
        has_swap = any(file_name in manifest["crops"] for manifest in manifests.values())
        if not has_swap:
            shutil.copy2(
                os.path.join(frames_dir, file_name),
                os.path.join(output_dir, file_name),
            )
        else:
            frame = cv2.imread(os.path.join(frames_dir, file_name))
            if frame is None:
                logger.warning("composite: could not read original frame %s, skipping", file_name)
                continue

            for face_id, manifest in manifests.items():
                if file_name not in manifest["crops"]:
                    continue

                swapped_crop_path = os.path.join(swapped_base_dir, face_id, file_name)
                if not os.path.exists(swapped_crop_path):
                    logger.debug("composite: missing swapped crop %s for %s", file_name, face_id)
                    continue

                swapped_crop = cv2.imread(swapped_crop_path)
                if swapped_crop is None:
                    logger.warning("composite: could not read swapped crop %s for %s", file_name, face_id)
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
            pct = int((index + 1) / total * 100)
            if pct >= last_log_pct + 10:
                logger.info("composite_swapped_faces: %d/%d frames (%.0f%%)", index + 1, total, pct)
                last_log_pct = pct
            _emit_progress(progress_callback, (index + 1) / total)

    logger.info("composite_swapped_faces: done — %d frames written to %s", total, output_dir)


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

    logger.info(
        "swap_faces_pipeline: %d face(s), %d swap frames, %d output frames, %d total work units",
        total_faces, total_swap_frames, total_output_frames, total_work_units,
    )

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
        logger.info(
            "swap_faces_pipeline: starting face %d/%d (%s) — %d frames",
            face_index, total_faces, face_id, face_frame_total,
        )

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

        swapped_count = len([
            f for f in os.listdir(swap_out)
            if f.startswith("frame_") and f.endswith(".jpg")
        ]) if os.path.isdir(swap_out) else 0
        logger.info(
            "swap_faces_pipeline: face %d/%d (%s) done — %d swapped frames produced, progress %.1f%%",
            face_index, total_faces, face_id, swapped_count,
            processed_swap_frames / total_work_units * 100,
        )

    logger.info("swap_faces_pipeline: all faces swapped, starting compositing of %d frames", total_output_frames)

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

    logger.info("swap_faces_pipeline: >>> starting composite_swapped_faces")
    composite_swapped_faces(
        frames_dir,
        output_dir,
        manifests,
        swapped_clips_dir,
        frame_names=output_frame_names,
        progress_callback=composite_progress,
    )
    logger.info("swap_faces_pipeline: <<< composite_swapped_faces done")
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
