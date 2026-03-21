import { useState } from "react";
import type { FaceInfo } from "../types";
import { Check } from "lucide-react";

interface FaceSelectorProps {
  faces: FaceInfo[];
  onSwap: (selectedIds: string[]) => void;
  isSwapping: boolean;
}

export function FaceSelector({ faces, onSwap, isSwapping }: FaceSelectorProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const toggleFace = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

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
    <div className="flex flex-col items-center gap-6 w-full max-w-2xl">
      <h2 className="text-xl font-semibold">Select faces to swap</h2>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 w-full">
        {faces.map((face) => {
          const isSelected = selected.has(face.face_id);
          return (
            <button
              key={face.face_id}
              onClick={() => toggleFace(face.face_id)}
              className={`relative rounded-xl overflow-hidden border-2 transition-all ${
                isSelected
                  ? "border-primary ring-2 ring-primary/30"
                  : "border-transparent hover:border-muted-foreground/30"
              }`}
            >
              <img
                src={face.thumbnail}
                alt={`Face ${face.face_id}`}
                className="w-full aspect-square object-cover"
              />
              {isSelected && (
                <div className="absolute top-2 right-2 w-6 h-6 bg-primary rounded-full flex items-center justify-center">
                  <Check className="w-4 h-4 text-primary-foreground" />
                </div>
              )}
              <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/70 to-transparent p-3">
                <div className="flex gap-2 text-xs text-white">
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
  );
}
