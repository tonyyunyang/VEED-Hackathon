"""
End-to-end integration test for the face-swap pipeline.

Exercises:  upload → detect-faces → swap → poll status → download

Prerequisites:
  1. FaceFusion API running on port 8001:
       cd facefusion && .venv/bin/python api.py
  2. Run from the server directory:
       cd VEED-Hackathon/server
       python -m pytest tests/test_face_swap.py -v -s
"""

import os
import time

import httpx
import pytest

VEED_BASE = "http://localhost:8000"
FACEFUSION_BASE = "http://localhost:8001"

TEST_VIDEO = os.path.join(
    os.path.dirname(__file__), "..", "..", "tests", "fixtures", "test_video.mp4"
)

POLL_INTERVAL = 3
POLL_TIMEOUT = 300  # 5 minutes max for a swap job


@pytest.fixture(scope="module")
def veed_client():
    return httpx.Client(base_url=VEED_BASE, timeout=30)


@pytest.fixture(scope="module")
def check_servers():
    """Fail fast if either server isn't reachable."""
    for name, url in [("VEED", VEED_BASE), ("FaceFusion", FACEFUSION_BASE)]:
        try:
            httpx.get(f"{url}/docs", timeout=5)
        except httpx.ConnectError:
            pytest.skip(f"{name} server not running at {url}")


@pytest.fixture(scope="module")
def check_video():
    if not os.path.exists(TEST_VIDEO):
        pytest.skip(f"Test video not found: {TEST_VIDEO}")


def test_face_swap_end_to_end(veed_client, check_servers, check_video):
    # ── 1. Upload ────────────────────────────────────────────────────────
    with open(TEST_VIDEO, "rb") as f:
        resp = veed_client.post("/api/upload", files={"file": ("test_video.mp4", f, "video/mp4")})
    assert resp.status_code == 200, resp.text
    video_id = resp.json()["video_id"]
    assert video_id

    # ── 2. Detect faces ─────────────────────────────────────────────────
    resp = veed_client.post("/api/detect-faces", json={"video_id": video_id})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["video_id"] == video_id
    faces = data["faces"]
    assert len(faces) > 0, "No faces detected in test video"

    face_id = faces[0]["face_id"]
    assert faces[0]["thumbnail"]  # base64 data-uri present
    assert faces[0]["frame_count"] > 0

    # ── 3. Swap ──────────────────────────────────────────────────────────
    resp = veed_client.post(
        "/api/swap", json={"video_id": video_id, "face_ids": [face_id]}
    )
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]
    assert job_id

    # ── 4. Poll status until completed ───────────────────────────────────
    start = time.time()
    last_progress = -1.0
    while True:
        resp = veed_client.get(f"/api/status/{job_id}")
        assert resp.status_code == 200, resp.text
        status = resp.json()

        assert status["status"] in ("pending", "processing", "completed", "failed")
        assert 0.0 <= status["progress"] <= 1.0

        if status["progress"] > last_progress:
            last_progress = status["progress"]

        if status["status"] == "completed":
            break

        if status["status"] == "failed":
            pytest.fail(f"Swap job failed: {status.get('error')}")

        elapsed = time.time() - start
        if elapsed > POLL_TIMEOUT:
            pytest.fail(f"Swap job timed out after {POLL_TIMEOUT}s (progress={status['progress']})")

        time.sleep(POLL_INTERVAL)

    assert status["progress"] == 1.0

    # ── 5. Download ──────────────────────────────────────────────────────
    resp = veed_client.get(f"/api/download/{job_id}")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "video/mp4"

    output_path = os.path.join(
        os.path.dirname(__file__), "..", "test_swap_output", "swapped_e2e.mp4"
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(resp.content)

    assert os.path.getsize(output_path) > 1000, "Output video suspiciously small"
    print(f"\nSwapped video saved to: {output_path}")
    print(f"  Size: {os.path.getsize(output_path) / 1024:.1f} KB")
