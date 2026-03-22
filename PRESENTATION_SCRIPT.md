# VEED Face Swap - Hackathon Presentation Script

---

## 1. THE PROBLEM (1-2 min)

**Open with the pain point:**

> "Every day, millions of videos are shared online — and in every one of them, there are faces. Faces of bystanders, faces of minors, faces of people who never consented to appear on camera.
> Preventing the face from going online without consent (for example, easy to be used afterwards for deepfakes, generating nude versions of it, or other malicious purposes — especially for minors).

> Today, if you need to mask someone's identity in a video — whether for privacy, legal compliance, or creative content — your options are terrible. You either blur the face, which screams 'something is hidden here' and destroys the viewing experience, or you spend hours in After Effects manually tracking and compositing frame by frame.

> On the other side, deepfake tools exist — but they're fragmented. You need one tool to detect faces, another to track them across frames, another to generate the replacement, another to render it back. And none of them give you precision — you can't say 'swap only this person's face, only in this 3-second segment.'

> We asked: **what if face swapping was as simple as uploading a video, clicking the faces you want to replace, and hitting swap?**"

---

## 2. THE SOLUTION — ONE-LINE PITCH (15 sec)

> "VEED Face Swap is an all-in-one video editor that detects, tracks, and swaps faces in any video — with frame-level precision and AI-generated replacements — in a single workspace."

---

## 3. LIVE DEMO WALKTHROUGH (4-5 min)

### Step 1: Upload (show Gallery page)

> "You start by uploading any video — MP4, MOV, WebM. Here's a clip with multiple people."

*Upload or select a demo video.*

### Step 2: Face Detection (show detection spinner, then results)

> "The system automatically extracts every frame, runs our face detection and tracking pipeline, and clusters faces by identity across the entire video — even across cuts and camera changes.

> Under the hood, this uses a SCRFD neural network for detection and OC-Sort tracking with shot-change detection. It handles jump cuts, multiple camera angles, and overlapping faces."

*Wait for detection to complete.*

### Step 3: Interactive Face Selection (show VideoPlayer with overlays)

> "Now look at this — every detected person gets a unique colored bounding box drawn directly on the video. You can hover to see metadata: age, gender, how many frames they appear in.

> I can click to select which faces I want to swap. Maybe I want to anonymize just this person — click. Or these two — click, click. The UI updates in real-time."

*Select 1-2 faces, show the colored borders and checkmarks.*

### Step 4: Timeline Trimming (show trim handles)

> "And here's where precision comes in. I don't have to swap the entire video. I can drag these handles to select exactly the segment I care about — maybe just this 5-second clip where someone walks through frame. The system only processes the frames I select."

*Drag the trim handles to show a sub-range.*

### Step 5: Reference Face — the AI Magic (show swap options)

> "Now — what face should we swap in? Three options:

> **Option A:** Upload your own reference image — a specific face you want to use.

> **Option B — and this is the cool part:** Let Runware AI generate a photorealistic replacement face. It reads the detected person's age and gender, then generates a neutral, passport-style portrait that matches their demographics. You can even add a style prompt — 'wearing sunglasses', 'with a beard' — and it adapts.

> **Option C:** We have a local reference library organized by age range and gender for fully offline operation."

*Show the upload option and/or mention the style prompt field.*

### Step 6: Processing (show progress screen)

> "Hit swap, and the pipeline kicks off. You can watch it in real-time — extracting face clips, swapping frame by frame, compositing back into the original video, then rendering the final output with the original audio preserved."

*Show the progress bar advancing through phases.*

### Step 7: Download (play the result)

> "And... done. Download the final video. The face is swapped, the audio is intact, and the person is completely unrecognizable — without a single blurred pixel."

*Play the output video.*

---

## 4. FEATURE RECAP (1 min)

> "Let me quickly recap what we built:

> 1. **Multi-face detection & tracking** — SCRFD + OC-Sort with shot-change handling, clusters faces across the entire video automatically.

> 2. **Interactive face selection** — Real-time bounding box overlays, age/gender metadata, click-to-select UI.

> 3. **Frame-level precision trimming** — Dual-handle timeline editor, swap only the segment you need.

> 4. **Smart reference resolution** — 5-level fallback chain: user upload, global config, Runware AI generation, age/gender-matched library, thumbnail fallback.

> 5. **AI face generation with Runware** — Demographically-aware prompt building, style customization, prompt injection protection.

> 6. **Pluggable swap backends** — InsightFace for speed, FaceFusion with HyperSwap for quality. Switch with one env variable.

> 7. **Full video pipeline** — Frame extraction, audio preservation, trimmed re-assembly — all handled by FFmpeg under the hood.

> 8. **Async processing with live status** — Non-blocking jobs, real-time phase tracking, frame-by-frame progress."

---

## 5. ARCHITECTURE — QUICK TECHNICAL SLIDE (30 sec)

> "Architecturally — React 19 frontend with canvas overlays, FastAPI backend with async job processing. The face tracking runs as a subprocess using our movie-like-shots package. Face swapping is pluggable: InsightFace ONNX models for local speed, or FaceFusion for production quality. Runware connects over WebSocket for AI generation. Everything is configurable through environment variables — 25+ config options, zero code changes to deploy."

---

## 6. CLOSING (15 sec)

> "We built this in one day, as a team of three. Identity masking doesn't have to mean blurring. Face swapping doesn't have to mean stitching five tools together. With VEED Face Swap, it's upload, click, swap, download. That's it."

---

## TIMING GUIDE

| Section | Duration |
|---------|----------|
| Problem | 1-2 min |
| One-liner | 15 sec |
| Live demo | 4-5 min |
| Feature recap | 1 min |
| Architecture | 30 sec |
| Closing | 15 sec |
| **Total** | **~8 min** |

## BACKUP TALKING POINTS (if asked)

- **Privacy/legal use case:** GDPR compliance, anonymizing bystanders in street footage, protecting minors
- **Creative use case:** Content creators swapping faces for comedy, character replacement
- **Security:** Style prompt is sanitized against injection, max 200 chars, blocked patterns
- **Why not just blur?** Blurring draws attention, ruins immersion, signals censorship. A natural-looking swap preserves the viewing experience
- **Lipsync:** We have a placeholder integration with VEED Fabric 1.0 for future lipsync capability
- **Scalability:** Async job queue, configurable thread counts, GPU acceleration via CoreML/CUDA
