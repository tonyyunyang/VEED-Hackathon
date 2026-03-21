import { Card } from "./ui/card";
import { Upload, Play, Plus, ChevronLeft, ChevronRight } from "lucide-react";
import React, { useRef, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { GalleryVideo } from "../types";
import { Button } from "./ui/button";

interface GalleryProps {
  videos: GalleryVideo[];
  onSelect: (src: string) => void;
  onUpload: (file: File) => void;
}

export function Gallery({ videos, onSelect, onUpload }: GalleryProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onUpload(file);
    }
  };

  const handleNext = () => {
    setActiveIndex((prev) => (prev + 1) % videos.length);
  };

  const handlePrev = () => {
    setActiveIndex((prev) => (prev - 1 + videos.length) % videos.length);
  };

  // Keyboard navigation
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") handleNext();
      if (e.key === "ArrowLeft") handlePrev();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [videos.length]);

  // Generate unique rotations and offsets for each video for a "natural" stack look
  const videoStyles = useMemo(() => {
    return videos.map((_, i) => ({
      rotate: (i % 2 === 0 ? 1 : -1) * (Math.random() * 3 + 1),
    }));
  }, [videos.length]);

  return (
    <div className="w-full max-w-5xl mx-auto min-h-[600px] flex flex-col items-center justify-center relative perspective-2000 py-10">
      {/* Hidden file input */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept="video/mp4,video/x-m4v,video/*"
        className="hidden"
      />

      <div className="relative w-full max-w-4xl h-[450px] flex items-center justify-center">
        {/* Navigation Arrows */}
        <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 flex justify-between px-4 md:-px-24 z-[150] pointer-events-none">
          <motion.div whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }} className="pointer-events-auto">
            <Button
              variant="ghost"
              size="icon"
              onClick={handlePrev}
              className="w-24 h-24 rounded-full bg-white/5 backdrop-blur-3xl border border-white/10 hover:bg-white/10 hover:border-white/20 text-white transition-all shadow-[0_0_50px_-12px_rgba(0,0,0,0.5)] group"
            >
              <ChevronLeft className="w-12 h-12 group-hover:-translate-x-1 transition-transform" />
            </Button>
          </motion.div>
          <motion.div whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }} className="pointer-events-auto">
            <Button
              variant="ghost"
              size="icon"
              onClick={handleNext}
              className="w-24 h-24 rounded-full bg-white/5 backdrop-blur-3xl border border-white/10 hover:bg-white/10 hover:border-white/20 text-white transition-all shadow-[0_0_50px_-12px_rgba(0,0,0,0.5)] group"
            >
              <ChevronRight className="w-12 h-12 group-hover:translate-x-1 transition-transform" />
            </Button>
          </motion.div>
        </div>

        <AnimatePresence initial={false}>
          {videos.map((video, i) => {
            // Calculate distance from active index
            const distance = i - activeIndex;
            
            // We only want to show a subset of the stack
            if (Math.abs(distance) > 3 && !(i === 0 && activeIndex === videos.length - 1) && !(i === videos.length - 1 && activeIndex === 0)) {
              return null;
            }

            return (
              <motion.div
                key={video.id + video.url}
                initial={{ opacity: 0, scale: 0.8, x: 200 }}
                animate={{ 
                  opacity: Math.abs(distance) > 2 ? 0 : 1 - Math.abs(distance) * 0.3, 
                  scale: 1 - Math.abs(distance) * 0.05, 
                  z: -Math.abs(distance) * 100,
                  x: distance * 40,
                  rotate: (videoStyles[i]?.rotate || 0) + distance * 2,
                  y: Math.abs(distance) * 10,
                }}
                exit={{ 
                  opacity: 0, 
                  scale: 0.5, 
                  x: distance < 0 ? -200 : 200,
                  rotate: distance < 0 ? -20 : 20,
                  transition: { duration: 0.3 }
                }}
                whileHover={distance === 0 ? { 
                  scale: 1.05,
                  y: -20,
                  transition: { duration: 0.2 }
                } : {}}
                transition={{ 
                  type: "spring",
                  stiffness: 260,
                  damping: 20
                }}
                style={{
                  zIndex: videos.length - Math.abs(distance),
                  position: 'absolute',
                  transformStyle: 'preserve-3d',
                  pointerEvents: distance === 0 ? 'auto' : 'none'
                }}
                className="w-[340px] md:w-[420px] rounded-3xl overflow-hidden shadow-2xl cursor-pointer group"
                onClick={() => distance === 0 && onSelect(video.url)}
              >
                <Card className="border-none bg-black/40 backdrop-blur-xl relative overflow-hidden ring-1 ring-white/10 group-hover:ring-primary/50 transition-all duration-500">
                  <div className="aspect-video bg-black relative flex items-center justify-center overflow-hidden">
                    <video
                      src={video.url}
                      className="w-full h-full object-cover opacity-60 group-hover:opacity-100 transition-opacity duration-700"
                      muted
                      onMouseEnter={(e) => distance === 0 && e.currentTarget.play()}
                      onMouseLeave={(e) => {
                        e.currentTarget.pause();
                        e.currentTarget.currentTime = 0;
                      }}
                    />
                    
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-100 transition-opacity" />
                    
                    {distance === 0 && (
                      <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none">
                        <div className="bg-white/10 backdrop-blur-xl rounded-full p-6 ring-1 ring-white/20 transform scale-75 group-hover:scale-100 transition-transform duration-500">
                          <Play className="w-10 h-10 text-white fill-white" />
                        </div>
                      </div>
                    )}

                    <div className="absolute top-4 right-4 bg-black/40 backdrop-blur-md rounded-full px-3 py-1 flex items-center gap-2 border border-white/10">
                      <div className={`w-2 h-2 rounded-full ${video.isUserUploaded ? 'bg-blue-400' : 'bg-primary'}`} />
                      <span className="text-[10px] font-bold text-white uppercase tracking-tighter">
                        {video.isUserUploaded ? 'User' : 'Sample'}
                      </span>
                    </div>
                  </div>

                  <div className="p-6">
                    <h3 className="text-xl font-bold text-white tracking-tight group-hover:text-primary transition-colors truncate">
                      {video.name}
                    </h3>
                    <div className="flex items-center justify-between mt-2">
                      <p className="text-xs text-white/40 font-medium uppercase tracking-widest">
                        {video.isUserUploaded ? "Custom Project" : "Built-in Preset"}
                      </p>
                      {distance === 0 && (
                        <div className="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                          <Plus className="w-4 h-4 text-white/50" />
                        </div>
                      )}
                    </div>
                  </div>
                </Card>
              </motion.div>
            );
          })}
        </AnimatePresence>

        {/* Global Floating Action Button for Upload */}
        <motion.button
          whileHover={{ scale: 1.1, rotate: 90 }}
          whileTap={{ scale: 0.9 }}
          onClick={handleUploadClick}
          className="fixed bottom-12 right-12 w-20 h-20 bg-primary text-white rounded-full shadow-2xl flex items-center justify-center z-[200] border-4 border-background ring-8 ring-primary/20"
        >
          <Upload className="w-8 h-8" />
        </motion.button>
      </div>

      {/* Pagination dots */}
      <div className="mt-12 flex gap-2">
        {videos.map((_, i) => (
          <button
            key={i}
            onClick={() => setActiveIndex(i)}
            className={`w-2 h-2 rounded-full transition-all duration-300 ${
              i === activeIndex ? "w-8 bg-primary" : "bg-white/20 hover:bg-white/40"
            }`}
          />
        ))}
      </div>
    </div>
  );
}
