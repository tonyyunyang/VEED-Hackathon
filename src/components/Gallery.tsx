import { Card } from "./ui/card";
import { Upload, Play } from "lucide-react";
import { Button } from "./ui/button";

interface GalleryProps {
  onSelect: (src: string) => void;
  onUploadClick: () => void;
}

export function Gallery({ onSelect, onUploadClick }: GalleryProps) {
  // Use Vite's glob import to get all videos from the projects folder
  const videoModules = import.meta.glob("../assets/video-projects/*.mp4", {
    eager: true,
    query: "?url",
    import: "default",
  });

  const videos = Object.entries(videoModules).map(([path, url]) => ({
    name: path.split("/").pop()?.replace(".mp4", "") || "Video",
    url: url as string,
    path,
  }));

  return (
    <div className="w-full max-w-6xl mx-auto p-6">
      <div className="flex justify-between items-center mb-8">
        <h2 className="text-2xl font-bold">Your Video Projects</h2>
        <Button onClick={onUploadClick} className="gap-2">
          <Upload className="w-4 h-4" />
          Upload New
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {videos.map((video) => (
          <Card
            key={video.path}
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
              <p className="text-xs text-muted-foreground mt-1 uppercase tracking-wider">
                Video Project
              </p>
            </div>
          </Card>
        ))}

        <div
          className="border-2 border-dashed border-muted-foreground/25 rounded-2xl aspect-video flex flex-col items-center justify-center gap-3 cursor-pointer hover:bg-muted/50 hover:border-primary/50 transition-all group"
          onClick={onUploadClick}
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
