# UI Integration: Reference Face Upload + Style Prompt

New backend features for face swap customization. No breaking changes — existing swap calls work unchanged.

## New Endpoint: Upload Reference Image

```
POST /api/upload-reference/{video_id}
Content-Type: multipart/form-data
```

**Request:** Send an image file as `file` field (accepts `.jpg`, `.jpeg`, `.png`, `.webp`).

```typescript
const formData = new FormData();
formData.append("file", imageFile);

const res = await fetch(`/api/upload-reference/${videoId}`, {
  method: "POST",
  body: formData,
});
// Response: { "video_id": "abc123", "reference_path": "uploaded_reference.jpg" }
```

**Behavior:**
- Saves the image to the video's storage directory
- Overwrites any previous upload for that video
- This image becomes the **highest priority** source face for all swaps on this video
- Call this **after** `/api/upload` and **before** `/api/swap`
- Optional — if not called, the backend falls through to Runware generation when a
  `style_prompt` is provided, or to the configured fallback references otherwise

**UI suggestion:** An optional "Upload reference face" button/dropzone on the face selection screen, shown after faces are detected.

---

## Updated Endpoint: Swap Request

```
POST /api/swap
Content-Type: application/json
```

**New optional field: `style_prompt`**

```typescript
// Before (still works, no changes needed):
{ "video_id": "abc123", "face_ids": ["face_0"] }

// New (optional style_prompt):
{
  "video_id": "abc123",
  "face_ids": ["face_0"],
  "style_prompt": "wearing sunglasses and face paint"
}
```

**`style_prompt` details:**
- Type: `string | null` (optional, defaults to `null`)
- Max 200 characters (truncated server-side)
- Appended to the AI generation prompt when Runware generates a face
- Only has effect when **no uploaded reference image** exists (Runware AI path)
- Sanitized server-side: special characters stripped, prompt injection blocked
- Example values: `"wearing sunglasses"`, `"with tribal face paint"`, `"with a beard"`, `"wearing a hat"`

**UI suggestion:** A text input labeled something like "Style description (optional)" near the swap button. Only shown when no reference image is uploaded.

---

## Resolution Priority (for context)

When the swap runs, the backend picks the source face using this order:

1. **Uploaded reference** — from `POST /api/upload-reference/{video_id}`
2. **Runware AI generation** — auto-generates a neutral face from the detected thumbnail, but only when `style_prompt` is provided
3. **Global env image** — `FACE_SWAP_REFERENCE_IMAGE` (server config, not UI-controlled)
4. **Reference library** — picks from `server/reference_faces/` by gender/age
5. **Thumbnail fallback** — reuses the detected face's own crop

If Runware fails, the backend falls through to the remaining fallback sources and
returns a warning so the UI can surface that fallback.

The UI only needs to care about #1 (upload) and #2 (style_prompt). The rest is backend config.

---

## TypeScript Types

```typescript
interface SwapRequest {
  video_id: string;
  face_ids: string[];
  start_frame?: number | null;
  end_frame?: number | null;
  style_prompt?: string | null; // NEW
}

interface UploadReferenceResponse {
  video_id: string;
  reference_path: string;
}
```

---

## Curl Examples

```bash
# Upload a reference face
curl -s -F "file=@face.jpg" http://localhost:8000/api/upload-reference/abc123

# Swap with style prompt (no reference uploaded)
curl -s -X POST http://localhost:8000/api/swap \
  -H "Content-Type: application/json" \
  -d '{"video_id":"abc123","face_ids":["face_0"],"style_prompt":"wearing aviator sunglasses"}'

# Swap with uploaded reference (style_prompt ignored since reference takes priority)
curl -s -X POST http://localhost:8000/api/swap \
  -H "Content-Type: application/json" \
  -d '{"video_id":"abc123","face_ids":["face_0"]}'
```
