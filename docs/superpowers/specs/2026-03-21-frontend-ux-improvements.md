# Frontend UX Improvements — Video Previews

## Goal

Add video playback at three points in the user flow: after file selection (preview before upload), during face selection (context for face thumbnails), and after swap completion (review result before downloading).

## Changes

### 1. New component: `VideoPreview.tsx`

Reusable video player component. Props:
- `src: string` — video URL (object URL for local files, API URL for results)
- `className?: string` — for layout sizing

Features:
- Native `<video>` element with `controls` attribute (no custom player needed)
- Rounded corners, max-height constrained
- `object-fit: contain` to handle any aspect ratio

### 2. Modified: `VideoUploader.tsx`

After file selection, show `VideoPreview` with a local object URL (`URL.createObjectURL(file)`).
- Video preview replaces the drop zone (no need to see both)
- Keep filename + size text below video
- Add a "Change video" text button to re-show the drop zone
- Revoke the object URL on unmount or file change

### 3. Modified: `FaceSelector.tsx`

Add `videoFile` prop (the original `File` object). Layout becomes two-panel:
- Left panel: `VideoPreview` showing the original video
- Right panel: face grid + swap button (existing UI)
- On small screens (`< md`): stack vertically, video on top

### 4. Modified: `ProcessingStatus.tsx`

On `completed` state:
- Show `VideoPreview` with `src={getDownloadUrl(jobId)}`
- Download button below the video player
- Layout: centered column, video on top, button below

### 5. Modified: `App.tsx`

- Store the selected `File` object in state (already done as local state in VideoUploader — lift to App)
- Pass `videoFile` to `FaceSelector`
- No new API endpoints needed — preview uses local object URLs, result uses existing `/api/download`

## Layout

```
Upload step (file selected):
┌──────────────────────┐
│   ┌──────────────┐   │
│   │  ▶ video     │   │
│   └──────────────┘   │
│   filename.mp4 (2MB) │
│   [Upload & Analyze] │
│   Change video       │
└──────────────────────┘

Face selection step:
┌────────────────┬─────────────────┐
│                │ Select faces    │
│   ▶ original   │ ┌───┐ ┌───┐    │
│     video      │ │ 😀│ │ 😀│    │
│                │ └───┘ └───┘    │
│                │ [Swap N faces] │
└────────────────┴─────────────────┘

Completed step:
┌──────────────────────┐
│   ┌──────────────┐   │
│   │  ▶ result    │   │
│   └──────────────┘   │
│   [Download Video]   │
│   [Start Over]       │
└──────────────────────┘
```

## No backend changes needed

All video sources are either local `File` objects (via `URL.createObjectURL`) or the existing `/api/download/{jobId}` endpoint.
