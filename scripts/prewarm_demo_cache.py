#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "server"))

import main  # noqa: E402
from services import face_tracker  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prewarm cached demo analysis artifacts and optional all-face output.",
    )
    parser.add_argument(
        "demo_id",
        help="Bundled demo clip ID, for example: party-10sec-preparation",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild the cached demo media directory even if it already matches the source clip.",
    )
    parser.add_argument(
        "--swap-all",
        action="store_true",
        help="Render and cache the full output video using all detected faces.",
    )
    parser.add_argument(
        "--force-output",
        action="store_true",
        help="Re-render the cached output even if output.mp4 already exists.",
    )
    parser.add_argument(
        "--style-prompt",
        default="",
        help="Optional style prompt to use when generating a cached all-face output.",
    )
    return parser


def _initial_job_state(job_id: str, media_id: str, media_type: str) -> dict:
    return {
        "status": "processing",
        "progress": 0.0,
        "error": None,
        "warnings": None,
        "video_id": media_id,
        "media_id": media_id,
        "media_type": media_type,
        "phase": "queued",
        "message": "Waiting to start",
        "completed_frames": 0,
        "total_frames": None,
        "output_filename": None,
    }


def _swap_cache_context(
    media_dir: Path,
    faces_json: dict,
    face_ids: list[str],
    style_prompt: str,
) -> tuple[dict, str]:
    frames_dir = media_dir / "frames"
    request_payload = main._swap_cache_request_payload(
        str(media_dir),
        faces_json,
        face_ids,
        0,
        len(main._frame_files(str(frames_dir))),
        style_prompt,
    )
    return request_payload, main._swap_cache_key(request_payload)


def _ensure_swap_cache_entry(
    media_dir: Path,
    faces_json: dict,
    face_ids: list[str],
    style_prompt: str,
    output_path: str,
    output_filename: str,
    warnings: list[str] | None = None,
) -> dict:
    request_payload, cache_key = _swap_cache_context(
        media_dir,
        faces_json,
        face_ids,
        style_prompt,
    )
    cached = main._lookup_cached_swap(str(media_dir), cache_key)
    if cached:
        return {
            "cache_key": cache_key,
            "cache_hit": True,
            "cached_output_path": cached.get("output_path"),
        }

    if not os.path.exists(output_path):
        return {
            "cache_key": cache_key,
            "cache_hit": False,
            "cached_output_path": None,
        }

    media_type = str(faces_json.get("media_type") or "video").lower()
    _resolved_output_path, output_media_type, _resolved_output_filename = (
        main._output_metadata_for_media(str(media_dir), faces_json)
    )
    cached_output_path = main._store_cached_swap(
        str(media_dir),
        cache_key,
        request_payload,
        output_path,
        output_filename,
        media_type,
        output_media_type,
        warnings,
    )
    return {
        "cache_key": cache_key,
        "cache_hit": False,
        "cached_output_path": cached_output_path,
    }


async def run(args: argparse.Namespace) -> dict:
    detection = main.ensure_demo_detection_cache(args.demo_id, force=args.force)
    media_id = detection.media_id
    media_dir = Path(main.STORAGE_DIR) / media_id
    faces_json = face_tracker.load_faces_json(str(media_dir / "faces.json"))
    face_ids = list(faces_json.get("faces", {}).keys())
    output_path, _mime_type, output_filename = main._output_metadata_for_media(
        str(media_dir),
        faces_json,
    )

    result = {
        "demo_id": args.demo_id,
        "media_id": media_id,
        "media_dir": str(media_dir),
        "source_video": str(main._demo_video_path(args.demo_id)),
        "face_count": len(face_ids),
        "face_ids": face_ids,
        "fps": detection.fps,
        "total_frames": detection.total_frames,
        "output_path": output_path,
        "output_filename": output_filename,
        "output_exists": os.path.exists(output_path),
    }

    if not args.swap_all:
        return result

    if not face_ids:
        result["swap"] = {
            "status": "skipped",
            "reason": "No faces were detected in the cached demo clip.",
        }
        return result

    if result["output_exists"] and not args.force_output and not args.force:
        cache_result = _ensure_swap_cache_entry(
            media_dir,
            faces_json,
            face_ids,
            args.style_prompt,
            output_path,
            output_filename,
        )
        result["swap"] = {
            "status": "skipped",
            "reason": "Cached output already exists.",
            **cache_result,
        }
        return result

    job_id = f"prewarm_{media_id}_all_faces"
    media_type = str(faces_json.get("media_type") or "video").lower()
    swap_request_payload, swap_cache_key = _swap_cache_context(
        media_dir,
        faces_json,
        face_ids,
        args.style_prompt,
    )
    main.jobs[job_id] = _initial_job_state(job_id, media_id, media_type)
    await main._run_swap_job(
        job_id,
        media_id,
        face_ids,
        None,
        None,
        args.style_prompt,
        swap_cache_key,
        swap_request_payload,
    )

    result["output_exists"] = os.path.exists(output_path)
    result["swap"] = {
        "job_id": job_id,
        **main.jobs.get(job_id, {}),
        **_ensure_swap_cache_entry(
            media_dir,
            faces_json,
            face_ids,
            args.style_prompt,
            output_path,
            output_filename,
            main.jobs.get(job_id, {}).get("warnings"),
        ),
    }
    return result


def cli() -> int:
    args = build_parser().parse_args()
    result = asyncio.run(run(args))
    print(json.dumps(result, indent=2))
    swap_status = result.get("swap", {}).get("status")
    if args.swap_all and swap_status == "failed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
