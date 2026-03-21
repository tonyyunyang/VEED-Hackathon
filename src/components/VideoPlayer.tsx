import React, { useRef, useEffect, useState, useMemo } from "react";
import videoData from "../assets/insightface_video_data.json";
import { Button } from "./ui/button";
import { Slider } from "./ui/slider";
import { Toolbar, ToolbarGroup } from "./ui/toolbar";
import { ToggleGroup, Toggle } from "./ui/toggle-group";
import {
  Tooltip,
  TooltipTrigger,
  TooltipPopup,
  TooltipProvider,
} from "./ui/tooltip";
import { Play, Pause, Scissors, Check, ScanFace } from "lucide-react";

const PERSON_COLORS = [
  "#00FF00", // Bright Green
  "#FF00FF", // Magenta
  "#00FFFF", // Cyan
  "#FFFF00", // Yellow
  "#FF4500", // OrangeRed
  "#ADFF2F", // GreenYellow
];

const getPersonColor = (id: number) => {
  return PERSON_COLORS[id % PERSON_COLORS.length];
};

interface VideoPlayerProps {
  videoSrc: string;
  onBack?: () => void;
}

export const VideoPlayer: React.FC<VideoPlayerProps> = ({
  videoSrc,
  onBack,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const [playing, setPlaying] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [selectionMode, setSelectionMode] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [faceControlMode, setFaceControlMode] = useState(false);
  const [selectedPersonIds, setSelectedPersonIds] = useState<number[]>([]);
  const [appliedSelectedIds, setAppliedSelectedIds] = useState<number[]>([]);

  // Selection state (timeframe isolation)
  const [startTime, setStartTime] = useState(0);
  const [endTime, setEndTime] = useState(0);

  // Temp selection for editing in selection mode
  const [tempSelection, setTempSelection] = useState<[number, number]>([0, 0]);
  const [keyframes, setKeyframes] = useState<string[]>([]);

  // Unique people metadata
  const personMetaData = useMemo(() => {
    const people: Record<number, any> = {};
    const sortedFrames = Object.keys(videoData.frames)
      .map(Number)
      .sort((a, b) => a - b);

    sortedFrames.forEach((frameIdx) => {
      const framePeople = (videoData.frames as any)[frameIdx.toString()];
      framePeople.forEach((p: any) => {
        if (!people[p.id]) {
          // If we haven't seen this person, or we find a better score (up to 1)
          people[p.id] = {
            id: p.id,
            label: p.label,
            bestFrameIndex: frameIdx,
            bbox: p.bbox,
            det_score: p.det_score,
            color: getPersonColor(p.id),
          };
        } else if (
          people[p.id].det_score < 1 &&
          p.det_score > people[p.id].det_score
        ) {
          people[p.id].bestFrameIndex = frameIdx;
          people[p.id].bbox = p.bbox;
          people[p.id].det_score = p.det_score;
        }
      });
    });
    return Object.values(people);
  }, []);

  const thumbnailCanvasesRef = useRef<Record<number, HTMLCanvasElement | null>>(
    {},
  );
  const hiddenVideoRef = useRef<HTMLVideoElement>(null);

  const generateThumbnails = async () => {
    const video = hiddenVideoRef.current;
    if (!video) return;

    for (const person of personMetaData) {
      const canvas = thumbnailCanvasesRef.current[person.id];
      if (!canvas) continue;

      const time = person.bestFrameIndex / videoData.video_metadata.fps;
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
    //setPlaying(false);
    //videoRef.current?.pause();
    setFaceControlMode(true);
    if (selectedPersonIds.length === 0) {
      setSelectedPersonIds(personMetaData.map((p) => p.id));
    }
  };

  const togglePersonSelection = (id: number) => {
    setSelectedPersonIds((prev) =>
      prev.includes(id) ? prev.filter((pid) => pid !== id) : [...prev, id],
    );
  };

  useEffect(() => {
    if (faceControlMode) {
      generateThumbnails();
    }
  }, [faceControlMode]);

  // Setup canvas drawing loop
  useEffect(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    let animationFrameId: number;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const renderFrame = () => {
      if (!video.paused && !video.ended) {
        const cw = canvas.width;
        const ch = canvas.height;
        const vw = video.videoWidth;
        const vh = video.videoHeight;

        if (vw > 0 && vh > 0) {
          const videoRatio = vw / vh;
          const canvasRatio = cw / ch;

          let drawWidth, drawHeight, dx, dy;

          if (videoRatio > canvasRatio) {
            drawWidth = cw;
            drawHeight = cw / videoRatio;
            dx = 0;
            dy = (ch - drawHeight) / 2;
          } else {
            drawWidth = ch * videoRatio;
            drawHeight = ch;
            dx = (cw - drawWidth) / 2;
            dy = 0;
          }

          ctx.clearRect(0, 0, cw, ch);
          ctx.drawImage(video, dx, dy, drawWidth, drawHeight);

          // DRAW BOUNDING BOXES
          const fps = videoData.video_metadata.fps;
          const origW = videoData.video_metadata.width;
          const currentFrame = Math.floor(video.currentTime * fps);
          const frameData = (videoData.frames as any)[currentFrame.toString()];

          if (frameData) {
            const scale = drawWidth / origW;

            frameData.forEach((person: any) => {
              if (
                (faceControlMode && !selectedPersonIds.includes(person.id)) ||
                (!faceControlMode &&
                  appliedSelectedIds.length > 0 &&
                  !appliedSelectedIds.includes(person.id))
              ) {
                return;
              }
              const [x1, y1, x2, y2] = person.bbox;
              const color = getPersonColor(person.id);

              ctx.strokeStyle = color;
              ctx.lineWidth = 3;
              ctx.strokeRect(
                dx + x1 * scale,
                dy + y1 * scale,
                (x2 - x1) * scale,
                (y2 - y1) * scale,
              );

              // Draw Label
              ctx.fillStyle = color;
              ctx.font = "bold 16px Inter, sans-serif";
              ctx.fillText(
                `${person.label} (${person.id})`,
                dx + x1 * scale,
                dy + y1 * scale - 10,
              );
            });
          }
        }
      }
      animationFrameId = requestAnimationFrame(renderFrame);
    };

    renderFrame();

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [faceControlMode, selectedPersonIds, appliedSelectedIds]);

  // Sync canvas size with parent
  useEffect(() => {
    const updateSize = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;

      // Initial frame draw if video is loaded
      const video = videoRef.current;
      if (video && video.videoWidth > 0) {
        const ctx = canvas.getContext("2d");
        if (ctx) {
          const cw = canvas.width;
          const ch = canvas.height;
          const vw = video.videoWidth;
          const vh = video.videoHeight;
          const videoRatio = vw / vh;
          const canvasRatio = cw / ch;

          let drawWidth, drawHeight, dx, dy;
          if (videoRatio > canvasRatio) {
            drawWidth = cw;
            drawHeight = cw / videoRatio;
            dx = 0;
            dy = (ch - drawHeight) / 2;
          } else {
            drawWidth = ch * videoRatio;
            drawHeight = ch;
            dx = (cw - drawWidth) / 2;
            dy = 0;
          }
          ctx.clearRect(0, 0, cw, ch);
          ctx.drawImage(video, dx, dy, drawWidth, drawHeight);
        }
      }
    };

    window.addEventListener("resize", updateSize);
    updateSize();
    return () => window.removeEventListener("resize", updateSize);
  }, []);

  // Handle video metadata
  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      const d = videoRef.current.duration;
      setDuration(d);
      setEndTime(d);
      setTempSelection([0, d]);
    }
  };

  // Handle time update
  const handleTimeUpdate = () => {
    if (videoRef.current) {
      const curr = videoRef.current.currentTime;
      setCurrentTime(curr);

      // If we've reached the end of the selection, pause or loop
      if (curr >= endTime && playing) {
        videoRef.current.pause();
        setPlaying(false);
      }
    }
  };

  // Autoplay on mount or src change
  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.play().catch((err) => {
        console.warn("Autoplay blocked or failed:", err);
        setPlaying(false);
      });
    }
  }, [videoSrc]);

  const togglePlay = () => {
    if (videoRef.current) {
      if (playing) {
        videoRef.current.pause();
      } else {
        // If we are at the end of selection, restart from startTime
        if (videoRef.current.currentTime >= endTime) {
          videoRef.current.currentTime = startTime;
        }
        videoRef.current.play();
      }
      setPlaying(!playing);
    }
  };

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

  // Scene Selection Mode: Generate Keyframes
  const enterSelectionMode = async () => {
    setSelectionMode(true);
    setTempSelection([0, duration]); // Reset to full duration

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
        offscreenCtx?.drawImage(
          video,
          0,
          0,
          offscreenCanvas.width,
          offscreenCanvas.height,
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
    setSelectionMode(false);
  };

  return (
    <div
      className="relative w-full h-screen overflow-hidden bg-black flex items-center justify-center"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
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

      <canvas
        ref={canvasRef}
        className="block"
        style={{ objectFit: "contain", maxWidth: "100%", maxHeight: "100%" }}
      />

      {/* Hover Controls */}
      <div
        className={`hover-controls absolute bottom-8 left-1/2 -translate-x-1/2 w-full max-w-4xl px-4 transition-all duration-500 ease-in-out ${
          hovered || selectionMode || faceControlMode
            ? "opacity-100"
            : "opacity-0 pointer-events-none"
        }`}
      >
        <TooltipProvider>
          <Toolbar
            className={`bg-background/80 backdrop-blur-md p-4 rounded-2xl border shadow-2xl flex flex-col gap-4 transition-all duration-500 ease-in-out overflow-hidden ${
              selectionMode || faceControlMode ? "max-w-5xl" : "max-w-4xl"
            }`}
          >
            {selectionMode ? (
              // Selection Mode Controls
              <div className="flex flex-col gap-6 w-full animate-in fade-in slide-in-from-bottom-4 duration-500">
                <div className="flex justify-between items-center">
                  <h3 className="text-lg font-semibold">Select Timeframe</h3>
                  <div className="flex flex-col items-end">
                    <span className="text-xs text-muted-foreground uppercase tracking-widest font-bold">
                      Range
                    </span>
                    <span className="text-sm font-mono font-bold">
                      {tempSelection[0].toFixed(2)}s —{" "}
                      {tempSelection[1].toFixed(2)}s
                    </span>
                  </div>
                </div>

                {/* Keyframe Strip */}
                <div className="relative w-full overflow-hidden bg-muted/30 rounded-xl p-1.5 flex gap-1 h-24 select-none group border border-white/5">
                  {keyframes.map((src, i) => (
                    <div key={i} className="relative h-full flex-1">
                      <img
                        src={src}
                        className="h-full w-full object-cover rounded-sm shadow-sm grayscale group-hover:grayscale-0 transition-all duration-300"
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

                  {/* Range Selection Overlay */}
                  <div className="absolute inset-x-3 inset-y-0 flex items-center">
                    <Slider
                      min={0}
                      max={duration}
                      step={0.1}
                      value={tempSelection}
                      onValueChange={(val) =>
                        setTempSelection(val as [number, number])
                      }
                      className="w-full z-10"
                    />
                  </div>
                </div>

                <div className="flex justify-end items-center gap-3">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSelectionMode(false)}
                    className="hover:bg-destructive/10 hover:text-destructive transition-colors"
                  >
                    Discard
                  </Button>
                  <Button
                    variant="default"
                    size="sm"
                    onClick={applySelection}
                    className="bg-primary hover:bg-primary/90 shadow-lg shadow-primary/20"
                  >
                    <Check className="w-4 h-4 mr-2" />
                    Accept Selection
                  </Button>
                </div>
              </div>
            ) : faceControlMode ? (
              // Face Control Mode Controls
              <div className="flex flex-col gap-6 w-full animate-in fade-in slide-in-from-bottom-4 duration-500">
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="text-lg font-semibold flex items-center gap-2">
                      Person Isolation
                    </h3>
                    <p className="text-xs text-muted-foreground font-medium">
                      Select unique individuals to track
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-6 overflow-x-auto pb-2 min-h-[140px] items-center justify-center">
                  {personMetaData.map((person) => (
                    <div
                      key={person.id}
                      onClick={() => togglePersonSelection(person.id)}
                      className={`relative cursor-pointer group transition-all duration-400 ${
                        selectedPersonIds.includes(person.id)
                          ? "scale-110"
                          : "opacity-40 grayscale scale-90 hover:opacity-70 hover:grayscale-0 hover:scale-95"
                      }`}
                    >
                      <div
                        className="w-24 h-24 rounded-md overflow-hidden border-4 transition-all duration-500 shadow-xl"
                        style={{
                          borderColor: selectedPersonIds.includes(person.id)
                            ? person.color
                            : "rgba(255,255,255,0.1)",
                          boxShadow: selectedPersonIds.includes(person.id)
                            ? `0 10px 25px -5px ${person.color}44`
                            : "none",
                        }}
                      >
                        <canvas
                          ref={(el) => {
                            thumbnailCanvasesRef.current[person.id] = el;
                          }}
                          width={100}
                          height={100}
                          className="w-full h-full object-cover"
                        />
                      </div>
                      <div
                        className="absolute -bottom-2 left-1/2 -translate-x-1/2 px-3 py-1 rounded-lg text-[10px] font-black text-white shadow-2xl whitespace-nowrap transition-transform duration-300 group-hover:scale-110"
                        style={{ backgroundColor: person.color }}
                      >
                        {person.label} #{person.id}
                      </div>

                      {selectedPersonIds.includes(person.id) && (
                        <div className="absolute -top-2 -right-2 bg-primary text-primary-foreground rounded-full p-1 shadow-lg animate-in zoom-in duration-300">
                          <Check className="w-3 h-3" />
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                <div className="flex justify-end items-center gap-3 pt-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setSelectedPersonIds(appliedSelectedIds);
                      setFaceControlMode(false);
                    }}
                    className="hover:bg-destructive/10 hover:text-destructive transition-colors px-6"
                  >
                    Discard
                  </Button>
                  <Button
                    variant="default"
                    size="sm"
                    onClick={() => {
                      setAppliedSelectedIds(selectedPersonIds);
                      setFaceControlMode(false);
                    }}
                    className="bg-primary hover:bg-primary/90 shadow-xl shadow-primary/20 px-8 font-bold"
                  >
                    <Check className="w-4 h-4 mr-2" />
                    Done
                  </Button>
                </div>
              </div>
            ) : (
              // Playback Mode Controls
              <div className="flex flex-col gap-4 w-full animate-in fade-in slide-in-from-top-2 duration-500">
                {/* Timeline / Scrubber */}
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

                {/* Controls Group */}
                <div className="flex items-center justify-between w-full px-2">
                  <ToolbarGroup className="flex items-center gap-3">
                    {onBack && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={onBack}
                        className="h-8"
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
                            className="h-10 w-10"
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

                    <div className="text-sm font-medium font-mono tabular-nums text-muted-foreground/80 bg-muted/50 px-3 py-1 rounded-full">
                      {currentTime.toFixed(2)}{" "}
                      <span className="text-muted-foreground/40 mx-1">/</span>{" "}
                      {duration.toFixed(2)}s
                    </div>
                  </ToolbarGroup>

                  <ToolbarGroup className="flex items-center gap-6">
                    <ToggleGroup
                      value={[playbackRate.toString()]}
                      onValueChange={changeSpeed}
                      className="bg-muted/30 p-1 rounded-lg border border-white/5"
                    >
                      <Toggle
                        value="0.5"
                        className="text-[10px] h-7 px-2 font-bold transition-all data-[state=on]:bg-background data-[state=on]:shadow-sm"
                      >
                        0.5x
                      </Toggle>
                      <Toggle
                        value="1"
                        className="text-[10px] h-7 px-2 font-bold transition-all data-[state=on]:bg-background data-[state=on]:shadow-sm"
                      >
                        1x
                      </Toggle>
                      <Toggle
                        value="2"
                        className="text-[10px] h-7 px-2 font-bold transition-all data-[state=on]:bg-background data-[state=on]:shadow-sm"
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
                            className="h-9 px-4 font-semibold shadow-sm hover:shadow-md transition-all active:scale-95"
                          >
                            <Scissors className="w-4 h-4 mr-2" />
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
                            className="h-9 px-4 font-semibold shadow-sm hover:shadow-md transition-all active:scale-95"
                          >
                            <ScanFace className="w-4 h-4 mr-2" />
                          </Button>
                        }
                      />
                      <TooltipPopup>Control Faces</TooltipPopup>
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
