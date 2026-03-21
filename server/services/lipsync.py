import os
import fal_client
from config import FAL_KEY, LIPSYNC_RESOLUTION


def apply_lipsync(
    face_image_path: str,
    audio_path: str,
    output_video_path: str,
) -> str:
    if not FAL_KEY:
        raise RuntimeError("FAL_KEY not set. Cannot use lipsync.")

    os.environ["FAL_KEY"] = FAL_KEY

    image_url = fal_client.upload_file(face_image_path)
    audio_url = fal_client.upload_file(audio_path)

    try:
        result = fal_client.subscribe(
            "veed/fabric-1.0",
            arguments={
                "image_url": image_url,
                "audio_url": audio_url,
                "resolution": LIPSYNC_RESOLUTION,
            },
        )
    except Exception as e:
        raise RuntimeError(f"VEED Fabric API failed: {e}")

    video_url = result.get("video", {}).get("url")
    if not video_url:
        raise RuntimeError("VEED Fabric returned no video URL")

    import httpx
    response = httpx.get(video_url)
    response.raise_for_status()
    with open(output_video_path, "wb") as f:
        f.write(response.content)

    return output_video_path
