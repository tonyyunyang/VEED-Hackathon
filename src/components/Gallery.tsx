import { Card } from "./ui/card";
import { Upload, Play } from "lucide-react";
import { Button } from "./ui/button";
import { useRef } from "react";
import type { GalleryVideo } from "../types";

interface GalleryProps {
  videos: GalleryVideo[];
  onSelect: (src: string) => void;
  onUpload: (file: File) => void;
}

export function Gallery({ videos, onSelect, onUpload }: GalleryProps) {
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

  return (
    <div className="w-full max-w-6xl mx-auto p-6">
      {/* Hidden file input */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept="video/mp4,video/x-m4v,video/*"
        className="hidden"
      />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {videos.map((video) => (
          <Card
            key={video.path + video.url}
            className="group relative overflow-hidden cursor-pointer hover:ring-2 hover:ring-primary transition-all rounded-2xl border-none shadow-lg bg-card"
            onClick={() => onSelect(video.url)}
          >
            <div className="aspect-video bg-black relative flex items-center justify-center overflow-hidden">
              <video
                src={video.url}
                className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity"
                muted
                onMouseEnter={(e) => e.currentTarget.play()}
                onMouseLeave={(e) => {
                  e.currentTarget.pause();
                  e.currentTarget.currentTime = 0;
                }}
              />
              <div className="absolute inset-0 bg-black/20 group-hover:bg-transparent transition-colors flex items-center justify-center pointer-events-none">
                <div className="bg-white/20 backdrop-blur-md rounded-full p-3 transform group-hover:scale-110 transition-transform">
                  <Play className="w-8 h-8 text-white fill-white" />
                </div>
              </div>
            </div>
            <div className="p-4 bg-background/50 backdrop-blur-sm">
              <p className="font-semibold text-foreground truncate">
                {video.name}
              </p>
              <div className="flex items-center justify-between mt-1">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">
                  {video.isUserUploaded ? "Uploaded Video" : "Built-in Sample"}
                </p>
              </div>
            </div>
          </Card>
        ))}

        <div
          className="border-2 border-dashed border-muted-foreground/25 rounded-2xl aspect-video flex flex-col items-center justify-center gap-3 cursor-pointer hover:bg-muted/50 hover:border-primary/50 transition-all group"
          onClick={handleUploadClick}
        >
          <div className="bg-muted rounded-full p-4 group-hover:bg-primary/10 group-hover:text-primary transition-colors">
            <Upload className="w-8 h-8" />
          </div>
          <span className="text-sm font-semibold">Upload New Video</span>
        </div>
      </div>
    </div>
  );
}
