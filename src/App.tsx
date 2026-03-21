import { useState } from "react";
import { Routes, Route, useNavigate, useParams, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import "./App.css";
import "./index.css";
import type { GalleryVideo } from "./types";
import { uploadVideo } from "./lib/utils/api";
import { Gallery } from "./components/Gallery";
import { VideoPlayer } from "./components/VideoPlayer";
import { Loader2 } from "lucide-react";

// Helper to create a URL-friendly slug
const slugify = (text: string) =>
  text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)+/g, "");

// Initial discover of built-in videos
const videoModules = import.meta.glob("./assets/video-projects/*.mp4", {
  eager: true,
  query: "?url",
  import: "default",
});

const initialVideos: GalleryVideo[] = Object.entries(videoModules).map(([path, url]) => {
  const fileName = path.split("/").pop()?.replace(".mp4", "") || "Video";
  return {
    id: slugify(fileName),
    name: fileName,
    url: url as string,
    path,
    isUserUploaded: false,
  };
});

// Helper component to handle dynamic video route
function VideoDetail({ allVideos }: { allVideos: GalleryVideo[] }) {
  const { videoId } = useParams();
  const navigate = useNavigate();
  const video = allVideos.find((v) => v.id === videoId);

  if (!video) {
    return (
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        className="flex flex-col items-center gap-4 mt-20"
      >
        <p className="text-xl font-bold">Video not found</p>
        <button onClick={() => navigate("/")} className="text-primary hover:underline">
          Go back to Gallery
        </button>
      </motion.div>
    );
  }

  return (
    <motion.div 
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 1.05 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="w-full h-screen fixed inset-0 z-50 bg-black"
    >
      <VideoPlayer videoSrc={video.url} onBack={() => navigate("/")} />
    </motion.div>
  );
}

function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const [allVideos, setAllVideos] = useState<GalleryVideo[]>(initialVideos);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = async (file: File) => {
    setIsUploading(true);
    setError(null);
    try {
      await uploadVideo(file);
      const url = URL.createObjectURL(file);
      const name = file.name.replace(/\.[^/.]+$/, "");
      const baseId = slugify(name);
      const id = `user-${baseId}-${Date.now()}`;
      
      const newVideo: GalleryVideo = {
        id,
        name,
        url: url,
        path: `user-upload-${id}`,
        isUserUploaded: true,
      };

      setAllVideos(prev => [newVideo, ...prev]);
      navigate("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="w-full min-h-screen bg-background font-sans flex flex-col items-center overflow-x-hidden">
      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
          <Route
            path="/"
            element={
              <motion.div
                initial={{ opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -30 }}
                transition={{ duration: 0.5, ease: "circOut" }}
                className="w-full flex flex-col items-center p-8"
              >
                <h1 className="text-5xl font-black mb-16 tracking-tighter bg-gradient-to-br from-foreground to-muted-foreground bg-clip-text text-transparent">
                  VEED Studio
                </h1>

                {error && (
                  <div className="mb-6 p-4 bg-destructive/10 text-destructive rounded-2xl text-sm max-w-lg w-full text-center border border-destructive/20 backdrop-blur-md">
                    {error}
                  </div>
                )}

                {isUploading && (
                  <div className="fixed inset-0 bg-background/40 backdrop-blur-xl z-[100] flex items-center justify-center">
                    <div className="flex flex-col items-center gap-4 p-8 rounded-3xl bg-card border shadow-2xl scale-110">
                      <Loader2 className="w-12 h-12 animate-spin text-primary" />
                      <p className="text-xl font-bold tracking-tight">Processing Masterpiece</p>
                    </div>
                  </div>
                )}

                <Gallery
                  videos={allVideos}
                  onSelect={(url) => {
                    const v = allVideos.find((v) => v.url === url);
                    if (v) navigate(`/video/${v.id}`);
                  }}
                  onUpload={handleUpload}
                />
              </motion.div>
            }
          />
          <Route path="/video/:videoId" element={<VideoDetail allVideos={allVideos} />} />
        </Routes>
      </AnimatePresence>
    </div>
  );
}

export default App;
