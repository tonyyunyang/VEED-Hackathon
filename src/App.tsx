import { useState } from "react";
import { Routes, Route, useNavigate, useParams } from "react-router-dom";
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
      <div className="flex flex-col items-center gap-4 mt-20">
        <p className="text-xl font-bold">Video not found</p>
        <button onClick={() => navigate("/")} className="text-primary hover:underline">
          Go back to Gallery
        </button>
      </div>
    );
  }

  return (
    <div className="w-full h-screen fixed inset-0 z-50">
      <VideoPlayer videoSrc={video.url} onBack={() => navigate("/")} />
    </div>
  );
}

function App() {
  const navigate = useNavigate();
  const [allVideos, setAllVideos] = useState<GalleryVideo[]>(initialVideos);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = async (file: File) => {
    setIsUploading(true);
    setError(null);
    try {
      // Step 1: Upload to server to get videoId (the underlying resource ID)
      await uploadVideo(file);

      // Step 2: Create a local preview
      const url = URL.createObjectURL(file);
      const name = file.name.replace(/\.[^/.]+$/, "");
      const baseId = slugify(name);
      const id = `user-${baseId}-${Date.now()}`; // Keep user prefix and timestamp for uniqueness
      
      const newVideo: GalleryVideo = {
        id,
        name,
        url: url,
        path: `user-upload-${id}`,
        isUserUploaded: true,
      };

      setAllVideos(prev => [newVideo, ...prev]);
      navigate("/"); // Ensure we are on gallery
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="w-full min-h-screen bg-background font-sans flex flex-col items-center p-8">
      <Routes>
        <Route
          path="/"
          element={
            <>
              <h1 className="text-4xl font-black mb-12 tracking-tight bg-gradient-to-r from-primary to-purple-600 bg-clip-text text-transparent">
                VEED Face Swapper
              </h1>

              {error && (
                <div className="mb-6 p-4 bg-destructive/10 text-destructive rounded-xl text-sm max-w-lg w-full text-center">
                  {error}
                </div>
              )}

              {isUploading && (
                <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-[100] flex items-center justify-center">
                  <div className="flex flex-col items-center gap-4">
                    <Loader2 className="w-10 h-10 animate-spin text-primary" />
                    <p className="text-lg font-medium">Uploading video...</p>
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
            </>
          }
        />
        <Route path="/video/:videoId" element={<VideoDetail allVideos={allVideos} />} />
      </Routes>
    </div>
  );
}

export default App;
