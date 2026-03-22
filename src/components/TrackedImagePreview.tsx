import { useState } from "react";
import type { BoundingBox, FaceInfo } from "../types";

interface TrackedImagePreviewProps {
  src: string;
  faces: FaceInfo[];
  selectedFaceIds?: string[];
  imageWidth?: number | null;
  imageHeight?: number | null;
  className?: string;
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

function firstBoundingBox(face: FaceInfo): BoundingBox | null {
  const frameKey = Object.keys(face.frames)
    .map(Number)
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b)[0];
  if (frameKey === undefined) {
    return null;
  }
  return face.frames[String(frameKey)] ?? null;
}

export function TrackedImagePreview({
  src,
  faces,
  selectedFaceIds = [],
  imageWidth,
  imageHeight,
  className = "",
}: TrackedImagePreviewProps) {
  const [naturalSize, setNaturalSize] = useState({ width: 0, height: 0 });
  const selectedSet = new Set(selectedFaceIds);
  const faceColors = Object.fromEntries(
    faces.map((face, index) => [
      face.face_id,
      FACE_COLORS[index % FACE_COLORS.length],
    ]),
  );
  const visibleFaces = faces
    .map((face) => ({
      face,
      bbox: firstBoundingBox(face),
    }))
    .filter(
      (
        entry,
      ): entry is {
        face: FaceInfo;
        bbox: BoundingBox;
      } => entry.bbox !== null,
    );

  const width = imageWidth ?? naturalSize.width;
  const height = imageHeight ?? naturalSize.height;

  return (
    <div className={`relative overflow-hidden rounded-[24px] bg-slate-950 ${className}`}>
      <img
        src={src}
        alt="Uploaded target"
        className="h-full w-full object-contain"
        onLoad={(event) => {
          setNaturalSize({
            width: event.currentTarget.naturalWidth,
            height: event.currentTarget.naturalHeight,
          });
        }}
      />

      {width > 0 && height > 0 && (
        <svg
          className="pointer-events-none absolute inset-0 h-full w-full"
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="xMidYMid meet"
          aria-hidden="true"
        >
          {visibleFaces.map(({ face, bbox }) => {
            const [x1, y1, x2, y2] = bbox;
            const color = faceColors[face.face_id] ?? "#ffffff";
            const isSelected =
              selectedSet.size === 0 || selectedSet.has(face.face_id);
            const labelY = Math.max(26, y1 - 8);

            return (
              <g key={face.face_id} opacity={isSelected ? 1 : 0.45}>
                <rect
                  x={x1}
                  y={y1}
                  width={Math.max(1, x2 - x1)}
                  height={Math.max(1, y2 - y1)}
                  fill="none"
                  stroke={color}
                  strokeWidth={isSelected ? 5 : 3}
                  rx={8}
                />
                <rect
                  x={x1}
                  y={labelY - 22}
                  width={92}
                  height={22}
                  rx={11}
                  fill={color}
                />
                <text
                  x={x1 + 11}
                  y={labelY - 7}
                  fill="#ffffff"
                  fontSize={12}
                  fontWeight={700}
                >
                  {face.face_id}
                </text>
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}
