import json


def generate_video_json():
    fps = 25
    duration_sec = 120
    total_frames = fps * duration_sec
    width, height = 1280, 720

    # Define starting positions and movement speeds (delta per frame)
    people = [
        {
            "id": 1,
            "label": "Person A",
            "start": [100, 100, 200, 220],
            "vel": [0.15, 0.05],
        },
        {
            "id": 2,
            "label": "Person B",
            "start": [800, 300, 910, 430],
            "vel": [-0.10, 0.12],
        },
        {
            "id": 3,
            "label": "Person C",
            "start": [500, 500, 595, 615],
            "vel": [0.05, -0.08],
        },
    ]

    frames_data = {}

    for f in range(total_frames):
        frame_faces = []
        for p in people:
            # Calculate new position based on frame index
            x1 = max(0, min(width, p["start"][0] + (p["vel"][0] * f)))
            y1 = max(0, min(height, p["start"][1] + (p["vel"][1] * f)))
            x2 = max(0, min(width, p["start"][2] + (p["vel"][0] * f)))
            y2 = max(0, min(height, p["start"][3] + (p["vel"][1] * f)))

            frame_faces.append(
                {
                    "bbox": [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)],
                    "id": p["id"],
                    "label": p["label"],
                    "det_score": 0.98,
                }
            )
        frames_data[str(f)] = frame_faces

    output = {
        "video_metadata": {
            "fps": fps,
            "width": width,
            "height": height,
            "total_frames": total_frames,
        },
        "frames": frames_data,
    }

    with open("insightface_video_data.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"Generated {total_frames} frames in 'insightface_video_data.json'")


generate_video_json()
