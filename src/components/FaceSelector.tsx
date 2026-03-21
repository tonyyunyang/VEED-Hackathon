import { useEffect, useMemo, useState } from "react";
import type { FaceInfo } from "../types";
import { Check } from "lucide-react";
import { TrackedVideoPreview } from "./TrackedVideoPreview";

interface FaceSelectorProps {
  faces: FaceInfo[];
  fps: number;
  videoFile: File | null;
  onSwap: (selectedIds: string[]) => void;
  isSwapping: boolean;
}

const FACE_COLORS = [
  "#ff6b6b",
  "#00c2ff",
  "#ffd166",
  "#06d6a0",
  "#f72585",
  "#8338ec",
  "#fb8500",
  "#3a86ff",
];

export function FaceSelector({
  faces,
  fps,
  videoFile,
  onSwap,
  isSwapping,
}: FaceSelectorProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!videoFile) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(videoFile);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [videoFile]);

  const toggleFace = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const faceColors = useMemo(
    () =>
      Object.fromEntries(
        faces.map((face, index) => [
          face.face_id,
          FACE_COLORS[index % FACE_COLORS.length],
        ]),
      ),
    [faces],
  );

  if (faces.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-xl font-medium text-muted-foreground">
          No faces detected
        </p>
        <p className="text-sm text-muted-foreground mt-2">
          Try uploading a different video
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col md:flex-row gap-8 w-full max-w-4xl">
      {/* Left: video preview */}
      {previewUrl && (
        <div className="flex-1 min-w-0">
          <TrackedVideoPreview
            src={previewUrl}
            faces={faces}
            fps={fps}
            faceColors={faceColors}
            selectedFaceIds={Array.from(selected)}
          />
        </div>
      )}

      {/* Right: face grid + swap button */}
      <div className="flex flex-col items-center gap-6 flex-1 min-w-0">
        <h2 className="text-xl font-semibold">Select faces to swap</h2>

        <div className="grid grid-cols-2 gap-4 w-full">
          {faces.map((face) => {
            const isSelected = selected.has(face.face_id);
            return (
              <button
                key={face.face_id}
                onClick={() => toggleFace(face.face_id)}
                style={{
                  borderColor: selected.has(face.face_id)
                    ? faceColors[face.face_id]
                    : undefined,
                  boxShadow: selected.has(face.face_id)
                    ? `0 0 0 3px ${faceColors[face.face_id]}33`
                    : undefined,
                }}
                className={`relative rounded-xl overflow-hidden border-2 transition-all ${
                  isSelected
                    ? ""
                    : "border-transparent hover:border-muted-foreground/30"
                }`}
              >
                <img
                  src={face.thumbnail}
                  alt={`Face ${face.face_id}`}
                  className="w-full aspect-square object-cover"
                />
                {isSelected && (
                  <div
                    className="absolute top-2 right-2 w-6 h-6 rounded-full flex items-center justify-center"
                    style={{ backgroundColor: faceColors[face.face_id] }}
                  >
                    <Check className="w-4 h-4 text-primary-foreground" />
                  </div>
                )}
                <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/70 to-transparent p-3">
                  <div className="flex gap-2 text-xs text-white">
                    <span
                      className="px-2 py-0.5 rounded-full font-semibold"
                      style={{ backgroundColor: faceColors[face.face_id] }}
                    >
                      {face.face_id}
                    </span>
                    <span className="bg-white/20 backdrop-blur-sm px-2 py-0.5 rounded-full">
                      {face.gender}, {face.age}y
                    </span>
                    <span className="bg-white/20 backdrop-blur-sm px-2 py-0.5 rounded-full">
                      {face.frame_count} frames
                    </span>
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        <button
          className="w-full max-w-xs py-3 px-6 bg-primary text-primary-foreground rounded-xl font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
          onClick={() => onSwap(Array.from(selected))}
          disabled={selected.size === 0 || isSwapping}
        >
          {isSwapping ? "Starting..." : `Swap ${selected.size} face(s)`}
        </button>
      </div>
    </div>
  );
}
