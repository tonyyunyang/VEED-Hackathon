import { useEffect, useMemo, useRef, useState } from "react";
import type { BoundingBox, FaceInfo } from "../types";

interface TrackedVideoPreviewProps {
  src: string;
  faces: FaceInfo[];
  fps: number;
  faceColors: Record<string, string>;
  selectedFaceIds?: string[];
  className?: string;
}

interface PreparedFace {
  face: FaceInfo;
  frameIndexes: number[];
}

function findBoundingBox(
  preparedFace: PreparedFace,
  frameIndex: number,
): BoundingBox | null {
  const exact = preparedFace.face.frames[String(frameIndex)];
  if (exact) {
    return exact;
  }

  let nearestFrame: number | null = null;
  let nearestDistance = Number.POSITIVE_INFINITY;
  for (const candidate of preparedFace.frameIndexes) {
    const distance = Math.abs(candidate - frameIndex);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestFrame = candidate;
    }
    if (candidate > frameIndex && distance > nearestDistance) {
      break;
    }
  }

  if (nearestFrame === null || nearestDistance > 1) {
    return null;
  }

  return preparedFace.face.frames[String(nearestFrame)] ?? null;
}

export function TrackedVideoPreview({
  src,
  faces,
  fps,
  faceColors,
  selectedFaceIds = [],
  className = "",
}: TrackedVideoPreviewProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentFrame, setCurrentFrame] = useState(0);
  const [videoSize, setVideoSize] = useState({ width: 0, height: 0 });

  const selectedSet = useMemo(
    () => new Set(selectedFaceIds),
    [selectedFaceIds],
  );

  const preparedFaces = useMemo<PreparedFace[]>(
    () =>
      faces.map((face) => ({
        face,
        frameIndexes: Object.keys(face.frames)
          .map(Number)
          .filter((value) => Number.isFinite(value))
          .sort((a, b) => a - b),
      })),
    [faces],
  );

  useEffect(() => {
    setCurrentFrame(0);
  }, [src, fps]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || fps <= 0) {
      return undefined;
    }

    let frameId = 0;
    const updateFrame = () => {
      const nextFrame = Math.max(0, Math.round(video.currentTime * fps));
      setCurrentFrame((previous) =>
        previous === nextFrame ? previous : nextFrame,
      );
      frameId = window.requestAnimationFrame(updateFrame);
    };

    frameId = window.requestAnimationFrame(updateFrame);
    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [fps, src]);

  const visibleFaces = useMemo(
    () =>
      preparedFaces
        .map((preparedFace) => ({
          face: preparedFace.face,
          bbox: findBoundingBox(preparedFace, currentFrame),
        }))
        .filter(
          (
            entry,
          ): entry is {
            face: FaceInfo;
            bbox: BoundingBox;
          } => entry.bbox !== null,
        ),
    [preparedFaces, currentFrame],
  );

  return (
    <div className="relative w-full overflow-hidden rounded-xl bg-black">
      <video
        ref={videoRef}
        src={src}
        controls
        className={`w-full rounded-xl bg-black object-contain max-h-[400px] ${className}`}
        onLoadedMetadata={(event) => {
          setVideoSize({
            width: event.currentTarget.videoWidth,
            height: event.currentTarget.videoHeight,
          });
        }}
      />

      {videoSize.width > 0 && videoSize.height > 0 && (
        <svg
          className="pointer-events-none absolute inset-0 h-full w-full"
          viewBox={`0 0 ${videoSize.width} ${videoSize.height}`}
          preserveAspectRatio="xMidYMid meet"
          aria-hidden="true"
        >
          {visibleFaces.map(({ face, bbox }) => {
            const [x1, y1, x2, y2] = bbox;
            const color = faceColors[face.face_id] ?? "#ffffff";
            const isSelected =
              selectedSet.size === 0 || selectedSet.has(face.face_id);
            const labelY = Math.max(24, y1 - 8);

            return (
              <g
                key={face.face_id}
                opacity={isSelected ? 1 : 0.45}
              >
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
                  y={labelY - 20}
                  width={86}
                  height={20}
                  rx={10}
                  fill={color}
                />
                <text
                  x={x1 + 10}
                  y={labelY - 6}
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

      {fps > 0 && (
        <div className="pointer-events-none absolute right-3 top-3 rounded-full bg-black/70 px-3 py-1 text-xs font-medium text-white">
          Frame {currentFrame} @ {fps.toFixed(1)} fps
        </div>
      )}
    </div>
  );
}
