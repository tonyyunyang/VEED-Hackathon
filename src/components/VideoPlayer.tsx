import React, { useRef, useEffect, useState, useMemo } from "react";
import { Slider as SliderPrimitive } from "@base-ui/react/slider";
import demoVideoData from "../assets/insightface_video_data.json";
import type { BoundingBox, FaceInfo } from "../types";
import { Button } from "./ui/button";
import { PartnerStrip } from "./PartnerStrip";
import { Slider } from "./ui/slider";
import { Toolbar, ToolbarGroup } from "./ui/toolbar";
import { ToggleGroup, Toggle } from "./ui/toggle-group";
import {
  Tooltip,
  TooltipTrigger,
  TooltipPopup,
  TooltipProvider,
} from "./ui/tooltip";
import {
  Play,
  Pause,
  Scissors,
  Check,
  ScanFace,
  SmilePlus,
  GripHorizontal,
  X,
  Film,
} from "lucide-react";

type PersonId = string;

interface TrackingEntry {
  id: PersonId;
  label: string;
  bbox: BoundingBox;
  det_score: number;
}

interface TrackingDataset {
  video_metadata: {
    fps: number;
    width?: number;
    height?: number;
    total_frames?: number;
  };
  frames: Record<string, TrackingEntry[]>;
}

interface PersonMeta {
  id: PersonId;
  label: string;
  bestFrameIndex: number;
  firstFrame: number;
  lastFrame: number;
  bbox: BoundingBox;
  det_score: number;
  color: string;
  thumbnailSrc?: string;
  age?: number;
  gender?: string;
  frameCount?: number;
}

/**
 * Generates a set of colors with high contrast between them and at least 4.6:1 contrast against black.
 * Uses HSL distribution and relative luminance calculation to ensure accessibility.
 */
const getRelativeLuminance = (r: number, g: number, b: number) => {
  const [rl, gl, bl] = [r, g, b].map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * rl + 0.7152 * gl + 0.0722 * bl;
};

const hslToRgb = (h: number, s: number, l: number) => {
  s /= 100;
  l /= 100;
  const k = (n: number) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) =>
    l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return [
    Math.round(255 * f(0)),
    Math.round(255 * f(8)),
    Math.round(255 * f(4)),
  ];
};

const generateAccessibleColors = (count: number): string[] => {
  const colors: string[] = [];
  const minLuminance = 0.18; // Required for ~4.6:1 contrast against black

  for (let i = 0; i < count; i++) {
    const h = (i * 360) / count;
    let s = 80; // High saturation for vibrancy
    let l = 50; // Start at middle lightness

    // Adjust lightness to ensure accessibility against black
    let [r, g, b] = hslToRgb(h, s, l);
    while (getRelativeLuminance(r, g, b) < minLuminance && l < 95) {
      l += 2;
      [r, g, b] = hslToRgb(h, s, l);
    }

    colors.push(`rgb(${r}, ${g}, ${b})`);
  }
  return colors;
};

/**
 * Calculates the bounding box for the video within the canvas, maintaining aspect ratio.
 */
interface VideoLayout {
  width: number;
  height: number;
  x: number;
  y: number;
}

const calculateVideoLayout = (
  cw: number,
  ch: number,
  vw: number,
  vh: number,
): VideoLayout => {
  if (vw <= 0 || vh <= 0) return { width: 0, height: 0, x: 0, y: 0 };

  const videoRatio = vw / vh;
  const canvasRatio = cw / ch;

  if (videoRatio > canvasRatio) {
    const width = cw;
    const height = cw / videoRatio;
    return { width, height, x: 0, y: (ch - height) / 2 };
  } else {
    const height = ch;
    const width = ch * videoRatio;
    return { width, height, x: (cw - width) / 2, y: 0 };
  }
};

/**
 * Draws the video frame to the canvas based on the calculated layout.
 */
const drawVideoFrame = (
  ctx: CanvasRenderingContext2D,
  video: HTMLVideoElement | HTMLImageElement,
  cw: number,
  ch: number,
  layout: VideoLayout,
) => {
  ctx.clearRect(0, 0, cw, ch);
  ctx.drawImage(video, layout.x, layout.y, layout.width, layout.height);
};

/**
 * Draws a person's bounding box and label.
 */
const drawPersonOverlay = (
  ctx: CanvasRenderingContext2D,
  person: TrackingEntry,
  layout: VideoLayout,
  scaleX: number,
  scaleY: number,
  color: string,
) => {
  const [x1, y1, x2, y2] = person.bbox;
  const bx = layout.x + x1 * scaleX;
  const by = layout.y + y1 * scaleY;
  const bw = (x2 - x1) * scaleX;
  const bh = (y2 - y1) * scaleY;

  ctx.strokeStyle = color;
  ctx.lineWidth = 3;
  ctx.strokeRect(bx, by, bw, bh);

  // Draw Label
  ctx.fillStyle = color;
  ctx.font = "bold 16px Inter, sans-serif";
  ctx.fillText(person.label, bx, Math.max(18, by - 10));
};

const frameArea = ([x1, y1, x2, y2]: BoundingBox) =>
  Math.max(0, x2 - x1) * Math.max(0, y2 - y1);

const buildTrackingDataFromFaces = (
  faces: FaceInfo[],
  fps: number,
): TrackingDataset => {
  const frames: Record<string, TrackingEntry[]> = {};

  faces.forEach((face) => {
    Object.entries(face.frames).forEach(([frameIndex, bbox]) => {
      frames[frameIndex] ??= [];
      frames[frameIndex].push({
        id: face.face_id,
        label: face.face_id,
        bbox,
        det_score: 1,
      });
    });
  });

  return {
    video_metadata: { fps },
    frames,
  };
};

const normalizeDemoTrackingData = (): TrackingDataset => ({
  video_metadata: demoVideoData.video_metadata,
  frames: Object.fromEntries(
    Object.entries(demoVideoData.frames).map(([frameIndex, people]) => [
      frameIndex,
      (people as Array<{
        id: number;
        label: string;
        bbox: BoundingBox;
        det_score?: number;
      }>).map((person) => ({
        id: String(person.id),
        label: person.label,
        bbox: person.bbox,
        det_score: person.det_score ?? 1,
      })),
    ]),
  ),
});

/**
 * Custom Range Selector with Bracket Handles
 */
const RangeBracketSelector = ({
  value,
  max,
  onChange,
}: {
  value: [number, number];
  max: number;
  onChange: (val: [number, number]) => void;
}) => {
  return (
    <SliderPrimitive.Root
      value={value}
      onValueChange={(val) => onChange(val as [number, number])}
      max={max}
      min={0}
      step={0.01}
      thumbAlignment="center"
      className="pointer-events-none relative flex h-full w-full items-center"
    >
      <SliderPrimitive.Control className="pointer-events-none relative flex h-full w-full items-center">
        <SliderPrimitive.Track className="pointer-events-none relative h-full w-full">
          {/* Selected Range Highlight */}
          <SliderPrimitive.Indicator className="slider-indicator absolute h-full bg-primary/10 border-y-2 border-primary/50 z-10" />

          {/* Left Bracket */}
          <SliderPrimitive.Thumb
            index={0}
            data-selection-handle="true"
            onPointerDownCapture={(event) => event.stopPropagation()}
            className="slider-thumb-frame pointer-events-auto absolute top-0 bottom-0 z-30 flex w-6 touch-none items-center justify-center cursor-ew-resize outline-none group"
          >
            <div className="slider-thumb__left h-full w-4 rounded-l-md border-l-4 border-y-4 border-primary transition-all duration-200" />
            {/* Grab handle dots */}
            <div className="absolute left-2 h-5 w-0.5 rounded-full bg-primary/65" />
          </SliderPrimitive.Thumb>

          {/* Right Bracket */}
          <SliderPrimitive.Thumb
            index={1}
            data-selection-handle="true"
            onPointerDownCapture={(event) => event.stopPropagation()}
            className="pointer-events-auto absolute top-0 bottom-0 z-30 flex w-6 touch-none items-center justify-center cursor-ew-resize outline-none group"
          >
            <div className="slider-thumb__right h-full w-4 rounded-r-md border-r-4 border-y-4 border-primary bg-primary/20 transition-all duration-200 group-hover:bg-primary/40" />
            {/* Grab handle dots */}
            <div className="absolute right-2 h-5 w-0.5 rounded-full bg-primary/65" />
          </SliderPrimitive.Thumb>
        </SliderPrimitive.Track>
      </SliderPrimitive.Control>
    </SliderPrimitive.Root>
  );
};

interface VideoPlayerProps {
  videoSrc: string;
  faces?: FaceInfo[];
  fps?: number;
  useLiveTracking?: boolean;
  error?: string | null;
  isSwapping?: boolean;
  onSwap?: (selectedIds: string[]) => void;
  onBack?: () => void;
}

export const VideoPlayer: React.FC<VideoPlayerProps> = ({
  videoSrc,
  faces = [],
  fps = 0,
  useLiveTracking = false,
  error = null,
  isSwapping = false,
  onSwap,
  onBack,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const facePanelDragRef = useRef<{
    originX: number;
    originY: number;
    startX: number;
    startY: number;
  } | null>(null);
  const selectionTimelineRef = useRef<HTMLDivElement>(null);

  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [selectionMode, setSelectionMode] = useState(false);
  const [faceControlMode, setFaceControlMode] = useState(false);
  const [selectedPersonIds, setSelectedPersonIds] = useState<PersonId[]>([]);
  const [appliedSelectedIds, setAppliedSelectedIds] = useState<PersonId[]>([]);
  const [hasFaceSelectionConfigured, setHasFaceSelectionConfigured] = useState(false);
  const [facePanelPosition, setFacePanelPosition] = useState({ x: 24, y: 118 });

  // Selection state (timeframe isolation)
  const [startTime, setStartTime] = useState(0);
  const [endTime, setEndTime] = useState(0);

  // Temp selection for editing in selection mode
  const [tempSelection, setTempSelection] = useState<[number, number]>([0, 0]);
  const [keyframes, setKeyframes] = useState<string[]>([]);

  const faceMetadataById = useMemo(
    () => new Map(faces.map((face) => [face.face_id, face])),
    [faces],
  );

  const trackingData = useMemo(
    () => (useLiveTracking ? buildTrackingDataFromFaces(faces, fps) : normalizeDemoTrackingData()),
    [faces, fps, useLiveTracking],
  );
  const clipDuration = Math.max(0, endTime - startTime);
  const relativeCurrentTime = Math.max(0, currentTime - startTime);
  const selectionDuration = Math.max(0.01, tempSelection[1] - tempSelection[0]);
  const selectionCurrentTime = Math.min(
    tempSelection[1],
    Math.max(tempSelection[0], currentTime),
  );
  const selectionProgress =
    duration > 0 ? Math.min(1, Math.max(0, selectionCurrentTime / duration)) : 0;
  const trackingFps = Math.max(trackingData.video_metadata.fps, 1);
  const clipStartFrame = Math.floor(startTime * trackingFps);
  const clipEndFrame = Math.ceil(endTime * trackingFps);

  // Unique people metadata
  const personMetaData = useMemo<PersonMeta[]>(() => {
    const people: Record<
      PersonId,
      Omit<PersonMeta, "color" | "thumbnailSrc" | "age" | "gender" | "frameCount">
    > = {};
    const sortedFrames = Object.keys(trackingData.frames)
      .map(Number)
      .sort((a, b) => a - b);

    sortedFrames.forEach((frameIdx) => {
      const framePeople = trackingData.frames[frameIdx.toString()] ?? [];
      framePeople.forEach((person) => {
        const existing = people[person.id];

        if (!existing) {
          people[person.id] = {
            id: person.id,
            label: person.label,
            bestFrameIndex: frameIdx,
            firstFrame: frameIdx,
            lastFrame: frameIdx,
            bbox: person.bbox,
            det_score: person.det_score,
          };
          return;
        }

        const shouldReplace =
          person.det_score > existing.det_score ||
          (person.det_score === existing.det_score &&
            frameArea(person.bbox) > frameArea(existing.bbox));

        people[person.id] = shouldReplace
          ? {
              ...existing,
              label: person.label,
              bestFrameIndex: frameIdx,
              bbox: person.bbox,
              det_score: person.det_score,
              firstFrame: Math.min(existing.firstFrame, frameIdx),
              lastFrame: Math.max(existing.lastFrame, frameIdx),
            }
          : {
              ...existing,
              firstFrame: Math.min(existing.firstFrame, frameIdx),
              lastFrame: Math.max(existing.lastFrame, frameIdx),
            };
      });
    });

    const peopleArray = Object.values(people).sort((a, b) =>
      a.bestFrameIndex === b.bestFrameIndex
        ? a.label.localeCompare(b.label)
        : a.bestFrameIndex - b.bestFrameIndex,
    );
    const colors = generateAccessibleColors(peopleArray.length);

    return peopleArray.map((p, index) => ({
      ...p,
      color: colors[index],
      thumbnailSrc: faceMetadataById.get(p.id)?.thumbnail,
      age: faceMetadataById.get(p.id)?.age,
      gender: faceMetadataById.get(p.id)?.gender,
      frameCount: faceMetadataById.get(p.id)?.frame_count,
    }));
  }, [trackingData, faceMetadataById]);

  const visiblePersonMetaData = useMemo(
    () =>
      personMetaData.filter(
        (person) =>
          person.firstFrame <= clipEndFrame && person.lastFrame >= clipStartFrame,
      ),
    [personMetaData, clipStartFrame, clipEndFrame],
  );
  const allVisibleFacesSelected =
    visiblePersonMetaData.length > 0 &&
    selectedPersonIds.length === visiblePersonMetaData.length;

  const getPersonColor = React.useCallback(
    (id: PersonId) => {
      const person = personMetaData.find((p) => p.id === id);
      return person?.color || "#FFFFFF";
    },
    [personMetaData],
  );

  const thumbnailCanvasesRef = useRef<Record<PersonId, HTMLCanvasElement | null>>(
    {},
  );
  const hiddenVideoRef = useRef<HTMLVideoElement>(null);

  const generateThumbnails = async () => {
    const video = hiddenVideoRef.current;
    if (!video) return;

    for (const person of visiblePersonMetaData) {
      if (person.thumbnailSrc) continue;

      const canvas = thumbnailCanvasesRef.current[person.id];
      if (!canvas) continue;

      const time = person.bestFrameIndex / Math.max(trackingData.video_metadata.fps, 1);
      video.currentTime = time;

      await new Promise((resolve) => {
        const onSeeked = () => {
          video.removeEventListener("seeked", onSeeked);
          const ctx = canvas.getContext("2d");
          if (ctx) {
            const [x1, y1, x2, y2] = person.bbox;
            const w = x2 - x1;
            const h = y2 - y1;
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(
              video,
              x1,
              y1,
              w,
              h,
              0,
              0,
              canvas.width,
              canvas.height,
            );
          }
          resolve(null);
        };
        video.addEventListener("seeked", onSeeked);
      });
    }
  };

  const enterFaceControlMode = () => {
    if (visiblePersonMetaData.length === 0) return;
    setFaceControlMode(true);
    if (!hasFaceSelectionConfigured && selectedPersonIds.length === 0) {
      const initialSelection = visiblePersonMetaData.map((p) => p.id);
      setSelectedPersonIds(initialSelection);
      setAppliedSelectedIds(initialSelection);
      setHasFaceSelectionConfigured(true);
      return;
    }

    setSelectedPersonIds(appliedSelectedIds);
  };

  const togglePersonSelection = (id: PersonId) => {
    setSelectedPersonIds((prev) => {
      const next = prev.includes(id)
        ? prev.filter((pid) => pid !== id)
        : [...prev, id];
      setAppliedSelectedIds(next);
      setHasFaceSelectionConfigured(true);
      return next;
    });
  };

  const handleSelectAllFaces = () => {
    if (allVisibleFacesSelected) {
      setSelectedPersonIds([]);
      setAppliedSelectedIds([]);
      setHasFaceSelectionConfigured(true);
      return;
    }
    const next = visiblePersonMetaData.map((person) => person.id);
    setSelectedPersonIds(next);
    setAppliedSelectedIds(next);
    setHasFaceSelectionConfigured(true);
  };

  const clampFacePanelPosition = (x: number, y: number) => {
    if (typeof window === "undefined") {
      return { x, y };
    }

    const panelWidth = 380;
    const panelHeight = Math.min(window.innerHeight - 40, 640);
    return {
      x: Math.min(Math.max(16, x), Math.max(16, window.innerWidth - panelWidth - 16)),
      y: Math.min(Math.max(16, y), Math.max(16, window.innerHeight - panelHeight - 16)),
    };
  };

  const handleFacePanelPointerDown = (
    event: React.PointerEvent<HTMLDivElement>,
  ) => {
    facePanelDragRef.current = {
      originX: facePanelPosition.x,
      originY: facePanelPosition.y,
      startX: event.clientX,
      startY: event.clientY,
    };
  };

  useEffect(() => {
    if (faceControlMode) {
      generateThumbnails();
    }
  }, [faceControlMode, visiblePersonMetaData, trackingData.video_metadata.fps]);

  useEffect(() => {
    const visibleIds = new Set(visiblePersonMetaData.map((person) => person.id));
    setSelectedPersonIds((prev) => prev.filter((id) => visibleIds.has(id)));
    setAppliedSelectedIds((prev) => prev.filter((id) => visibleIds.has(id)));
  }, [visiblePersonMetaData]);

  useEffect(() => {
    if (!selectionMode) return;
    const clampedTime = Math.min(
      tempSelection[1],
      Math.max(tempSelection[0], currentTime),
    );
    if (Math.abs(clampedTime - currentTime) > 0.001) {
      seekToTime(clampedTime);
    }
  }, [selectionMode, tempSelection, currentTime]);

  useEffect(() => {
    const handlePointerMove = (event: PointerEvent) => {
      const drag = facePanelDragRef.current;
      if (!drag) return;

      setFacePanelPosition(
        clampFacePanelPosition(
          drag.originX + (event.clientX - drag.startX),
          drag.originY + (event.clientY - drag.startY),
        ),
      );
    };

    const stopDragging = () => {
      facePanelDragRef.current = null;
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", stopDragging);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", stopDragging);
    };
  }, []);

  useEffect(() => {
    setSelectionMode(false);
    setFaceControlMode(false);
    setSelectedPersonIds([]);
    setAppliedSelectedIds([]);
    setHasFaceSelectionConfigured(false);
    setFacePanelPosition({ x: 24, y: 118 });
    setKeyframes([]);
    setCurrentTime(0);
    setDuration(0);
    setStartTime(0);
    setEndTime(0);
    setTempSelection([0, 0]);
  }, [videoSrc, faces, fps, useLiveTracking]);

  // Setup canvas drawing loop
  useEffect(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    let animationFrameId: number;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const renderFrame = () => {
      const layout = calculateVideoLayout(
        canvas.width,
        canvas.height,
        video.videoWidth,
        video.videoHeight,
      );

      if (layout.width > 0) {
        drawVideoFrame(ctx, video, canvas.width, canvas.height, layout);

        // DRAW BOUNDING BOXES
        const currentFrame = Math.round(
          video.currentTime * Math.max(trackingData.video_metadata.fps, 1),
        );
        const frameData =
          trackingData.frames[currentFrame.toString()] ??
          trackingData.frames[(currentFrame + 1).toString()] ??
          trackingData.frames[(currentFrame - 1).toString()];

        if (frameData) {
          const scaleX = layout.width / Math.max(video.videoWidth, 1);
          const scaleY = layout.height / Math.max(video.videoHeight, 1);
          frameData.forEach((person) => {
            if (
              (faceControlMode && !selectedPersonIds.includes(person.id)) ||
              (!faceControlMode &&
                hasFaceSelectionConfigured &&
                !appliedSelectedIds.includes(person.id))
            ) {
              return;
            }
            drawPersonOverlay(
              ctx,
              person,
              layout,
              scaleX,
              scaleY,
              getPersonColor(person.id),
            );
          });
        }
      }

      animationFrameId = requestAnimationFrame(renderFrame);
    };

    renderFrame();

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [
    faceControlMode,
    selectedPersonIds,
    appliedSelectedIds,
    hasFaceSelectionConfigured,
    getPersonColor,
    trackingData,
  ]);

  // Sync canvas size with parent
  useEffect(() => {
    const updateSize = () => {
      const stage = stageRef.current;
      const canvas = canvasRef.current;
      if (!canvas || !stage) return;

      const bounds = stage.getBoundingClientRect();
      canvas.width = Math.max(1, Math.round(bounds.width));
      canvas.height = Math.max(1, Math.round(bounds.height));

      // Initial frame draw if video is loaded
      const video = videoRef.current;
      if (video && video.videoWidth > 0) {
        const ctx = canvas.getContext("2d");
        if (ctx) {
          const layout = calculateVideoLayout(
            canvas.width,
            canvas.height,
            video.videoWidth,
            video.videoHeight,
          );
          drawVideoFrame(ctx, video, canvas.width, canvas.height, layout);
        }
      }
    };

    const observer =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(updateSize)
        : null;

    if (stageRef.current && observer) {
      observer.observe(stageRef.current);
    }

    updateSize();
    return () => observer?.disconnect();
  }, []);

  const handleFaceSwap = () => {
    const chosenIds = hasFaceSelectionConfigured ? appliedSelectedIds : [];

    if (chosenIds.length === 0) {
      enterFaceControlMode();
      return;
    }

    if (onSwap) {
      onSwap(chosenIds);
      return;
    }

    const exportData = {
      video_metadata: trackingData.video_metadata,
      frames: Object.entries(trackingData.frames).reduce(
        (acc: Record<string, TrackingEntry[]>, [frameIdx, people]) => {
          const filteredPeople = people.filter((person) =>
            chosenIds.includes(person.id),
          );

          if (filteredPeople.length > 0) {
            acc[frameIdx] = filteredPeople;
          }
          return acc;
        },
        {},
      ),
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "selected_faces.json";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };
  // Handle video metadata
  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      const d = videoRef.current.duration;
      setDuration(d);
      setEndTime(d);
      setTempSelection([0, d]);
      videoRef.current.currentTime = 0;
      videoRef.current.pause();
      setCurrentTime(0);
      setPlaying(false);
    }
  };

  // Handle time update
  const handleTimeUpdate = () => {
    if (videoRef.current) {
      const curr = videoRef.current.currentTime;
      setCurrentTime(curr);

      if (selectionMode && playing && curr >= tempSelection[1]) {
        videoRef.current.pause();
        videoRef.current.currentTime = tempSelection[0];
        setCurrentTime(tempSelection[0]);
        setPlaying(false);
        return;
      }

      if (curr >= endTime && playing) {
        videoRef.current.pause();
        videoRef.current.currentTime = startTime;
        setCurrentTime(startTime);
        setPlaying(false);
      }
    }
  };

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.currentTime = 0;
      setCurrentTime(0);
      setPlaying(false);
    }
  }, [videoSrc]);

  const togglePlay = () => {
    if (videoRef.current) {
      if (playing) {
        videoRef.current.pause();
      } else {
        const playbackStart = selectionMode ? tempSelection[0] : startTime;
        const playbackEnd = selectionMode ? tempSelection[1] : endTime;

        if (
          videoRef.current.currentTime < playbackStart ||
          videoRef.current.currentTime >= playbackEnd
        ) {
          videoRef.current.currentTime = playbackStart;
          setCurrentTime(playbackStart);
        }
        videoRef.current.play();
      }
      setPlaying(!playing);
    }
  };

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.code !== "Space") return;
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }

      event.preventDefault();
      togglePlay();
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [playing, selectionMode, startTime, endTime, tempSelection]);

  const handleScrub = (value: number | readonly number[]) => {
    const val = Array.isArray(value) ? value[0] : value;
    if (videoRef.current) {
      videoRef.current.currentTime = val;
      setCurrentTime(val);
    }
  };

  const changeSpeed = (value: string[]) => {
    const speed = parseFloat(value[0]);
    if (videoRef.current && !isNaN(speed)) {
      videoRef.current.playbackRate = speed;
      setPlaybackRate(speed);
    }
  };

  const seekToTime = (time: number) => {
    const nextTime = Math.min(duration, Math.max(0, time));
    if (videoRef.current) {
      videoRef.current.currentTime = nextTime;
    }
    setCurrentTime(nextTime);
  };

  const handleSelectionTimelinePointer = (
    event: React.PointerEvent<HTMLDivElement>,
  ) => {
    if (
      event.target instanceof HTMLElement &&
      event.target.closest("[data-selection-handle='true']")
    ) {
      return;
    }

    const bounds = selectionTimelineRef.current?.getBoundingClientRect();
    if (!bounds) return;

    const ratio = Math.min(
      1,
      Math.max(0, (event.clientX - bounds.left) / Math.max(1, bounds.width)),
    );
    const nextTime = duration * ratio;
    seekToTime(Math.min(tempSelection[1], Math.max(tempSelection[0], nextTime)));
  };

  // Scene Selection Mode: Generate Keyframes
  const enterSelectionMode = async () => {
    setSelectionMode(true);
    setFaceControlMode(false);
    setPlaying(false);
    videoRef.current?.pause();
    setTempSelection([startTime, endTime]);
    seekToTime(startTime);

    // Generate keyframes if not already done
    if (keyframes.length === 0) {
      const frames = [];
      const video = videoRef.current;
      if (!video) return;

      const offscreenCanvas = document.createElement("canvas");
      offscreenCanvas.width = 160;
      offscreenCanvas.height = 90;
      const offscreenCtx = offscreenCanvas.getContext("2d");

      const originalTime = video.currentTime;
      for (let i = 0; i < 10; i++) {
        const time = (duration / 10) * i;
        video.currentTime = time;
        await new Promise((resolve) => {
          video.onseeked = resolve;
        });

        const layout = calculateVideoLayout(
          offscreenCanvas.width,
          offscreenCanvas.height,
          video.videoWidth,
          video.videoHeight,
        );
        drawVideoFrame(
          offscreenCtx!,
          video,
          offscreenCanvas.width,
          offscreenCanvas.height,
          layout,
        );
        frames.push(offscreenCanvas.toDataURL());
      }
      video.currentTime = originalTime;
      setKeyframes(frames);
    }
  };

  const applySelection = () => {
    setStartTime(tempSelection[0]);
    setEndTime(tempSelection[1]);
    if (videoRef.current) {
      videoRef.current.currentTime = tempSelection[0];
    }
    setCurrentTime(tempSelection[0]);
    setPlaying(false);
    setSelectionMode(false);
  };

  const activeDuration = clipDuration > 0 ? clipDuration : duration;
  const appliedFaceCount = visiblePersonMetaData.filter((person) =>
    appliedSelectedIds.includes(person.id),
  ).length;

  return (
    <div className="relative h-screen w-full overflow-hidden bg-[radial-gradient(circle_at_top_left,_rgba(167,255,124,0.18),_transparent_24%),radial-gradient(circle_at_top_right,_rgba(122,87,255,0.2),_transparent_28%),radial-gradient(circle_at_bottom_left,_rgba(255,111,97,0.14),_transparent_26%),linear-gradient(180deg,_#050816_0%,_#0a1020_100%)] text-white">
      <video
        ref={videoRef}
        src={videoSrc}
        className="hidden"
        onLoadedMetadata={handleLoadedMetadata}
        onTimeUpdate={handleTimeUpdate}
        muted={false}
      />

      <video
        ref={hiddenVideoRef}
        src={videoSrc}
        className="hidden"
        preload="auto"
      />

      {error && (
        <div className="absolute top-6 left-1/2 z-30 w-full max-w-xl -translate-x-1/2 px-4">
          <div className="rounded-2xl border border-red-500/30 bg-red-500/15 px-4 py-3 text-center text-sm font-medium text-red-100 backdrop-blur-md">
            {error}
          </div>
        </div>
      )}

      <div className="relative z-10 flex h-full flex-col px-5 py-5 md:px-8 md:py-7">
        <div className="flex items-start justify-between gap-4">
          <div className="max-w-xl rounded-3xl border border-white/10 bg-white/6 px-5 py-4 shadow-[0_24px_80px_rgba(0,0,0,0.35)] backdrop-blur-xl">
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-white/55">
              <Film className="h-3.5 w-3.5" />
              Editor
            </div>
            <h2 className="text-xl font-semibold tracking-tight text-white">
              {useLiveTracking
                ? "Review detection before swapping"
                : "Preview tracked faces"}
            </h2>
            <p className="mt-1 text-sm text-white/60">
              {useLiveTracking
                ? "Pause, trim, and choose faces from the same editor before starting the backend swap."
                : "Demo mode uses the bundled sample tracking data and editor controls."}
            </p>
            <PartnerStrip compact className="mt-4" />
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2">
            <div className="rounded-full border border-white/10 bg-white/6 px-3 py-1.5 text-xs font-medium text-white/70 backdrop-blur-md">
              {useLiveTracking ? "Live detection" : "Demo preview"}
            </div>
            <div className="rounded-full border border-white/10 bg-white/6 px-3 py-1.5 text-xs font-medium text-white/70 backdrop-blur-md">
              {visiblePersonMetaData.length} faces in clip
            </div>
            <div className="rounded-full border border-white/10 bg-white/6 px-3 py-1.5 text-xs font-medium text-white/70 backdrop-blur-md">
              clip {activeDuration.toFixed(2)}s
            </div>
            {useLiveTracking && (
              <div className="rounded-full border border-white/10 bg-white/6 px-3 py-1.5 text-xs font-medium text-white/70 backdrop-blur-md">
                {appliedFaceCount} faces selected
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-1 items-center justify-center py-6 md:py-8">
          <div
            ref={stageRef}
            className="relative aspect-video w-full max-w-[980px] overflow-hidden rounded-[32px] border border-white/10 bg-black/75 shadow-[0_40px_120px_rgba(0,0,0,0.5)] ring-1 ring-white/5"
            style={{ width: "min(70vw, 980px)", maxHeight: "68vh" }}
          >
            <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.04),transparent_22%,transparent_78%,rgba(255,255,255,0.04))]" />
            <div className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-black/35 to-transparent" />
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/55 to-transparent" />
            <canvas
              ref={canvasRef}
              className="block h-full w-full"
            />
          </div>
        </div>
      </div>

      {faceControlMode && (
        <div
          className="absolute z-30 w-[360px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-[28px] border border-white/10 bg-slate-950/90 shadow-[0_32px_90px_rgba(0,0,0,0.55)] backdrop-blur-2xl"
          style={{
            left: facePanelPosition.x,
            top: facePanelPosition.y,
          }}
        >
          <div
            onPointerDown={handleFacePanelPointerDown}
            className="flex cursor-move items-center justify-between border-b border-white/10 px-4 py-3"
          >
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <GripHorizontal className="h-4 w-4 text-white/45" />
              Face picker
            </div>
            <button
              onClick={() => setFaceControlMode(false)}
              className="rounded-full p-1.5 text-white/55 transition-colors hover:bg-white/10 hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex items-center justify-between px-4 py-3 text-xs text-white/55">
            <span>
              Click faces to include them in the swap.
            </span>
            <span>{selectedPersonIds.length} selected</span>
          </div>

          <div className="max-h-[52vh] overflow-y-auto px-4 pb-4">
            {visiblePersonMetaData.length === 0 ? (
              <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-10 text-center text-sm text-white/55">
                No tracked faces overlap this trimmed range.
              </div>
            ) : (
              <div className="grid grid-cols-3 gap-3">
                {visiblePersonMetaData.map((person) => {
                  const isSelected = selectedPersonIds.includes(person.id);
                  return (
                    <button
                      key={person.id}
                      onClick={() => togglePersonSelection(person.id)}
                      className="group text-left"
                    >
                      <div
                        className={`relative overflow-hidden rounded-2xl border-2 transition-all ${
                          isSelected
                            ? "scale-[1.02] shadow-[0_10px_30px_rgba(0,0,0,0.25)]"
                            : "border-white/10 opacity-70 hover:opacity-100"
                        }`}
                        style={{
                          borderColor: isSelected ? person.color : undefined,
                          boxShadow: isSelected
                            ? `0 14px 32px -18px ${person.color}`
                            : undefined,
                        }}
                      >
                        <div className="aspect-square bg-black">
                          {person.thumbnailSrc ? (
                            <img
                              src={person.thumbnailSrc}
                              alt={person.label}
                              className="h-full w-full object-cover"
                            />
                          ) : (
                            <canvas
                              ref={(el) => {
                                thumbnailCanvasesRef.current[person.id] = el;
                              }}
                              width={96}
                              height={96}
                              className="h-full w-full object-cover"
                            />
                          )}
                        </div>
                        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-2 py-2">
                          <div className="flex items-center justify-between gap-2">
                            <span
                              className="rounded-full px-2 py-0.5 text-[10px] font-bold text-white"
                              style={{ backgroundColor: person.color }}
                            >
                              {person.label}
                            </span>
                            {person.frameCount !== undefined && (
                              <span className="text-[10px] font-medium text-white/70">
                                {person.frameCount}f
                              </span>
                            )}
                          </div>
                        </div>
                        {isSelected && (
                          <div className="absolute right-2 top-2 rounded-full bg-slate-900/85 p-1 text-white shadow-lg">
                            <Check className="h-3.5 w-3.5" />
                          </div>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div className="flex items-center justify-between border-t border-white/10 px-4 py-3">
            <div className="flex w-full items-center justify-between gap-3">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleSelectAllFaces}
                disabled={visiblePersonMetaData.length === 0}
                className="text-white/65 hover:bg-white/8 hover:text-white"
              >
                {allVisibleFacesSelected ? "Deselect all" : "Select all"}
              </Button>
              <div className="rounded-full border border-white/10 bg-white/6 px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.18em] text-white/50">
                Selection updates live
              </div>
            </div>
          </div>
        </div>
      )}

      <div
        className={`absolute bottom-6 left-1/2 z-20 w-full -translate-x-1/2 px-4 ${
          selectionMode ? "max-w-4xl" : "max-w-5xl"
        }`}
      >
        <TooltipProvider>
          <Toolbar
            className="rounded-[28px] border border-white/10 bg-slate-950/78 p-4 shadow-[0_30px_90px_rgba(0,0,0,0.45)] backdrop-blur-2xl"
          >
            {selectionMode ? (
              <div className="flex flex-col gap-6 w-full animate-in fade-in slide-in-from-bottom-4 duration-500">
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="text-lg font-semibold text-white">
                      Edit timeframe
                    </h3>
                    <p className="mt-1 text-sm text-white/55">
                      Drag the brackets, then preview only the selected part before applying it.
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={togglePlay}
                      className="bg-white/8 text-white hover:bg-white/14"
                    >
                      {playing ? (
                        <Pause className="mr-2 h-4 w-4" />
                      ) : (
                        <Play className="mr-2 h-4 w-4" />
                      )}
                      Preview selection
                    </Button>
                    <div className="rounded-full border border-white/10 bg-white/6 px-3 py-1.5 text-sm font-mono font-semibold text-white/80">
                      {Math.max(0, currentTime - tempSelection[0]).toFixed(2)}s
                      <span className="mx-1 text-white/35">/</span>
                      {(tempSelection[1] - tempSelection[0]).toFixed(2)}s
                    </div>
                  </div>
                </div>

                <div
                  ref={selectionTimelineRef}
                  className="relative h-20 w-full select-none overflow-hidden rounded-xl border border-white/5 bg-muted/30 p-1.5 touch-none"
                  onPointerDown={(event) => {
                    event.preventDefault();
                    event.currentTarget.setPointerCapture(event.pointerId);
                    handleSelectionTimelinePointer(event);
                  }}
                  onPointerMove={(event) => {
                    if (event.buttons === 1) {
                      handleSelectionTimelinePointer(event);
                    }
                  }}
                >
                  <div className="flex h-full gap-1">
                    {keyframes.map((src, i) => (
                      <div key={i} className="relative h-full flex-1">
                        <img
                          src={src}
                          className="h-full w-full rounded-sm object-cover shadow-sm grayscale group-hover:grayscale-0 transition-all duration-300"
                          alt={`Keyframe ${i}`}
                        />
                        <div
                          className={`absolute inset-0 bg-black/50 transition-opacity duration-300 ${
                            (i / keyframes.length) * duration <
                              tempSelection[0] ||
                            ((i + 1) / keyframes.length) * duration >
                              tempSelection[1]
                              ? "opacity-100"
                              : "opacity-0"
                          }`}
                        />
                      </div>
                    ))}
                  </div>

                  <div className="absolute inset-0 flex items-center">
                    <RangeBracketSelector
                      max={duration}
                      value={tempSelection}
                      onChange={(val) => setTempSelection(val)}
                    />
                  </div>

                  <div
                    className="absolute inset-y-0 z-20 w-8 -translate-x-1/2 cursor-ew-resize touch-none"
                    style={{ left: `${selectionProgress * 100}%` }}
                    onPointerDown={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      event.currentTarget.setPointerCapture(event.pointerId);
                      handleSelectionTimelinePointer(event);
                    }}
                    onPointerMove={(event) => {
                      if (event.buttons === 1) {
                        handleSelectionTimelinePointer(event);
                      }
                    }}
                  >
                    <div className="absolute inset-y-1 left-1/2 w-0.5 -translate-x-1/2 rounded-full bg-white shadow-[0_0_0_1px_rgba(255,255,255,0.14),0_0_24px_rgba(255,255,255,0.22)]" />
                    <div className="absolute left-1/2 top-0 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/20 bg-white shadow-lg" />
                    <div className="absolute left-1/2 bottom-0 h-3.5 w-3.5 -translate-x-1/2 translate-y-1/2 rounded-full border border-white/20 bg-white shadow-lg" />
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="rounded-full border border-white/10 bg-white/6 px-3 py-1.5 text-xs font-medium text-white/65">
                      Range {tempSelection[0].toFixed(2)}s — {tempSelection[1].toFixed(2)}s
                    </div>
                    <div className="rounded-full border border-white/10 bg-white/6 px-3 py-1.5 text-xs font-medium text-white/65">
                      Preview {Math.max(0, currentTime - tempSelection[0]).toFixed(2)}s / {selectionDuration.toFixed(2)}s
                    </div>
                  </div>

                  <div className="flex items-center justify-between gap-3">
                    <div className="rounded-full border border-white/10 bg-white/6 px-3 py-1.5 text-xs font-medium text-white/65">
                      Drag the white playhead within the selected range to preview frame-by-frame. Press space to play or pause from anywhere.
                    </div>
                    <div className="flex items-center gap-3">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setSelectionMode(false);
                          setPlaying(false);
                          videoRef.current?.pause();
                        }}
                        className="text-white/65 hover:bg-white/8 hover:text-white"
                      >
                        Discard
                      </Button>
                      <Button
                        size="sm"
                        onClick={applySelection}
                        className="bg-white text-slate-950 hover:bg-white/90"
                      >
                        <Check className="w-4 h-4 mr-2" />
                        Accept Selection
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-4 w-full animate-in fade-in slide-in-from-top-2 duration-500">
                <div className="w-full h-2 flex items-center px-2">
                  <Slider
                    min={startTime}
                    max={endTime}
                    step={0.01}
                    value={[currentTime]}
                    onValueChange={handleScrub}
                    className="flex-1"
                  />
                </div>

                <div className="flex items-center justify-between w-full px-2">
                  <ToolbarGroup className="flex items-center gap-3">
                    {onBack && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={onBack}
                        className="h-8 text-white/80 hover:bg-white/8 hover:text-white"
                      >
                        Back
                      </Button>
                    )}
                    <Tooltip>
                      <TooltipTrigger
                        render={
                          <Button
                            size="icon"
                            variant="ghost"
                            onClick={togglePlay}
                            className="h-10 w-10 text-white hover:bg-white/8"
                          >
                            {playing ? (
                              <Pause className="w-5 h-5 fill-current" />
                            ) : (
                              <Play className="w-5 h-5 fill-current ml-0.5" />
                            )}
                          </Button>
                        }
                      />
                      <TooltipPopup>{playing ? "Pause" : "Play"}</TooltipPopup>
                    </Tooltip>

                    <div className="rounded-full border border-white/10 bg-white/6 px-3 py-1 text-sm font-medium font-mono tabular-nums text-white/80">
                      {relativeCurrentTime.toFixed(2)}{" "}
                      <span className="mx-1 text-white/35">/</span>{" "}
                      {activeDuration.toFixed(2)}s
                    </div>
                  </ToolbarGroup>

                  <ToolbarGroup className="flex items-center gap-6">
                    <ToggleGroup
                      value={[playbackRate.toString()]}
                      onValueChange={changeSpeed}
                      className="rounded-xl border border-white/10 bg-white/6 p-1"
                    >
                      <Toggle
                        value="0.5"
                        className="h-8 min-w-12 rounded-lg border border-transparent px-3 text-[11px] font-semibold text-white/62 transition-all hover:text-white data-[pressed]:border-white/15 data-[pressed]:bg-white data-[pressed]:text-slate-950 data-[pressed]:shadow-sm"
                      >
                        0.5x
                      </Toggle>
                      <Toggle
                        value="1"
                        className="h-8 min-w-12 rounded-lg border border-transparent px-3 text-[11px] font-semibold text-white/62 transition-all hover:text-white data-[pressed]:border-white/15 data-[pressed]:bg-white data-[pressed]:text-slate-950 data-[pressed]:shadow-sm"
                      >
                        1.0x
                      </Toggle>
                      <Toggle
                        value="2"
                        className="h-8 min-w-12 rounded-lg border border-transparent px-3 text-[11px] font-semibold text-white/62 transition-all hover:text-white data-[pressed]:border-white/15 data-[pressed]:bg-white data-[pressed]:text-slate-950 data-[pressed]:shadow-sm"
                      >
                        2x
                      </Toggle>
                    </ToggleGroup>

                    <Tooltip>
                      <TooltipTrigger
                        render={
                          <Button
                            size="sm"
                            onClick={enterSelectionMode}
                            className="h-9 px-4 font-semibold text-white shadow-sm transition-all active:scale-95 hover:bg-white/8"
                          >
                            <Scissors className="w-4 h-4 mr-2" />
                            Timeframe
                          </Button>
                        }
                      />
                      <TooltipPopup>Edit timeframe</TooltipPopup>
                    </Tooltip>

                    <Tooltip>
                      <TooltipTrigger
                        render={
                          <Button
                            size="sm"
                            onClick={enterFaceControlMode}
                            className={`h-9 px-4 font-semibold text-white shadow-sm transition-all active:scale-95 hover:bg-white/8 ${
                              faceControlMode ? "bg-white/12" : ""
                            }`}
                          >
                            <ScanFace className="w-4 h-4 mr-2" />
                            Faces
                          </Button>
                        }
                      />
                      <TooltipPopup>Control Faces</TooltipPopup>
                    </Tooltip>

                    <Tooltip>
                      <TooltipTrigger
                        render={
                          <Button
                            size="sm"
                            onClick={handleFaceSwap}
                            disabled={isSwapping}
                            className="h-9 px-4 bg-white font-semibold text-slate-950 shadow-sm transition-all active:scale-95 hover:bg-white/90 disabled:bg-white/45"
                          >
                            <SmilePlus className="w-4 h-4 mr-2" />
                            {onSwap
                              ? appliedFaceCount > 0
                                ? `Swap ${appliedFaceCount} Face${appliedFaceCount === 1 ? "" : "s"}`
                                : "Swap Selected"
                              : "Export Selection"}
                          </Button>
                        }
                      />
                      <TooltipPopup>
                        {isSwapping
                          ? "Starting swap..."
                          : onSwap
                            ? "Open Faces to choose people, then start the backend swap"
                            : "Export the selected face tracks"}
                      </TooltipPopup>
                    </Tooltip>
                  </ToolbarGroup>
                </div>
              </div>
            )}
          </Toolbar>
        </TooltipProvider>
      </div>
    </div>
  );
};
