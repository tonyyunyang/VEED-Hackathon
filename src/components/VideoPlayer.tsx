import React, { useRef, useEffect, useState } from 'react';
import videoSrc from '../assets/video-ref.mp4';
import { Button } from './ui/button';
import { Slider } from './ui/slider';
import { Toolbar, ToolbarGroup } from './ui/toolbar';
import { ToggleGroup, Toggle } from './ui/toggle-group';
import { Tooltip, TooltipTrigger, TooltipPopup, TooltipProvider } from './ui/tooltip';
import { Play, Pause, Scissors, Check, X } from 'lucide-react';

interface VideoPlayerProps {
  // Add props if needed
}

export const VideoPlayer: React.FC<VideoPlayerProps> = () => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [selectionMode, setSelectionMode] = useState(false);
  const [hovered, setHovered] = useState(false);
  
  // Selection state (timeframe isolation)
  const [startTime, setStartTime] = useState(0);
  const [endTime, setEndTime] = useState(0);
  
  // Temp selection for editing in selection mode
  const [tempSelection, setTempSelection] = useState<[number, number]>([0, 0]);
  const [keyframes, setKeyframes] = useState<string[]>([]);

  // Setup canvas drawing loop
  useEffect(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    const ctx = canvas.getContext('2d');
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
        }
      }
      requestAnimationFrame(renderFrame);
    };

    renderFrame();
  }, []);

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
        const ctx = canvas.getContext('2d');
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

    window.addEventListener('resize', updateSize);
    updateSize();
    return () => window.removeEventListener('resize', updateSize);
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

      const offscreenCanvas = document.createElement('canvas');
      offscreenCanvas.width = 160;
      offscreenCanvas.height = 90;
      const offscreenCtx = offscreenCanvas.getContext('2d');

      const originalTime = video.currentTime;
      for (let i = 0; i < 10; i++) {
        const time = (duration / 10) * i;
        video.currentTime = time;
        await new Promise(resolve => {
          video.onseeked = resolve;
        });
        offscreenCtx?.drawImage(video, 0, 0, offscreenCanvas.width, offscreenCanvas.height);
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
      
      <canvas
        ref={canvasRef}
        className="block"
        style={{ objectFit: 'contain', maxWidth: '100%', maxHeight: '100%' }}
      />

      {/* Hover Controls */}
      <div className={`absolute bottom-8 left-1/2 -translate-x-1/2 w-full max-w-4xl px-4 transition-opacity duration-300 ${hovered || selectionMode ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}>
        <TooltipProvider>
          <Toolbar className="bg-background/80 backdrop-blur-md p-4 rounded-2xl border shadow-2xl flex flex-col gap-4">
            
            {/* Timeline / Scrubber */}
            {!selectionMode && (
              <div className="w-full h-8 flex items-center px-4">
                <Slider 
                  min={startTime} 
                  max={endTime} 
                  step={0.01}
                  value={[currentTime]} 
                  onValueChange={handleScrub}
                  className="flex-1"
                />
              </div>
            )}

            {/* Controls Group */}
            <div className="flex items-center justify-between w-full px-4">
              <ToolbarGroup className="flex items-center gap-2">
                <Tooltip>
                  <TooltipTrigger render={
                    <Button size="icon" variant="ghost" onClick={togglePlay}>
                      {playing ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6" />}
                    </Button>
                  } />
                  <TooltipPopup>{playing ? "Pause" : "Play"}</TooltipPopup>
                </Tooltip>
                
                <div className="text-xs font-mono tabular-nums text-muted-foreground ml-2">
                  {currentTime.toFixed(2)} / {duration.toFixed(2)}s
                </div>
              </ToolbarGroup>

              <ToolbarGroup className="flex items-center gap-4">
                <ToggleGroup type="single" value={[playbackRate.toString()]} onValueChange={changeSpeed}>
                  <Toggle value="0.5" className="text-xs px-2">0.5x</Toggle>
                  <Toggle value="1" className="text-xs px-2">1x</Toggle>
                  <Toggle value="2" className="text-xs px-2">2x</Toggle>
                </ToggleGroup>

                <Tooltip>
                  <TooltipTrigger render={
                    <Button 
                      variant={selectionMode ? "secondary" : "outline"} 
                      size="sm" 
                      onClick={selectionMode ? () => setSelectionMode(false) : enterSelectionMode}
                    >
                      <Scissors className="w-4 h-4 mr-2" />
                      {selectionMode ? "Cancel" : "Scene Selection"}
                    </Button>
                  } />
                  <TooltipPopup>Scene Selection</TooltipPopup>
                </Tooltip>
              </ToolbarGroup>
            </div>
          </Toolbar>
        </TooltipProvider>
      </div>

      {/* Scene Selection Mode Overlay */}
      {selectionMode && (
        <div className="absolute inset-0 z-50 bg-black/60 backdrop-blur-sm flex flex-col items-center justify-center p-8 animate-in fade-in zoom-in duration-300">
           <div className="bg-background border rounded-3xl p-8 max-w-5xl w-full flex flex-col gap-6 shadow-2xl">
              <div className="flex justify-between items-center">
                <h3 className="text-xl font-semibold">Select Timeframe</h3>
                <Button variant="ghost" size="icon" onClick={() => setSelectionMode(false)}>
                  <X className="w-6 h-6" />
                </Button>
              </div>

              {/* Keyframe Strip */}
              <div className="relative w-full overflow-hidden bg-muted rounded-xl p-2 flex gap-1 h-32 select-none group">
                {keyframes.map((src, i) => (
                  <div key={i} className="relative h-full flex-1">
                    <img src={src} className="h-full w-full object-cover rounded shadow-sm grayscale group-hover:grayscale-0 transition-all" />
                    {/* Visual Mask for out-of-range areas */}
                    <div className={`absolute inset-0 bg-black/40 transition-opacity ${
                      (i / keyframes.length) * duration < tempSelection[0] || 
                      ((i + 1) / keyframes.length) * duration > tempSelection[1] 
                      ? 'opacity-100' : 'opacity-0'
                    }`} />
                  </div>
                ))}
                
                {/* Range Selection Overlay */}
                <div className="absolute inset-x-4 inset-y-0 flex items-center">
                   <Slider 
                     min={0} 
                     max={duration} 
                     step={0.1}
                     value={tempSelection} 
                     onValueChange={(val) => setTempSelection(val as [number, number])}
                     className="w-full z-10"
                   />
                </div>
              </div>

              <div className="flex justify-between items-center">
                <div className="flex flex-col gap-1">
                  <span className="text-sm text-muted-foreground uppercase tracking-widest font-semibold">Range</span>
                  <span className="text-lg font-mono">
                    {tempSelection[0].toFixed(2)}s — {tempSelection[1].toFixed(2)}s
                  </span>
                </div>
                
                <div className="flex gap-2">
                   <Button variant="outline" onClick={() => setSelectionMode(false)}>Discard</Button>
                   <Button variant="default" onClick={applySelection}>
                     <Check className="w-4 h-4 mr-2" />
                     Accept Selection
                   </Button>
                </div>
              </div>
           </div>
        </div>
      )}
    </div>
  );
};
