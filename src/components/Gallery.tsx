import { useRef, useState } from "react";
import { Card } from "./ui/card";
import { Upload, Play, ScanFace } from "lucide-react";

interface GalleryProps {
  onSelect: (src: string | File) => void;
  onUserUpload: (file: File) => void;
  onImageFlowClick: () => void;
  userVideos: { name: string; url: string; file: File }[];
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function GalleryVideoCard({
  video,
  onSelect,
}: {
  video: { name: string; url: string; file: File | null; isStatic: boolean };
  onSelect: (src: string | File) => void;
}) {
  const [duration, setDuration] = useState<number | null>(null);

  const handleLoadedMetadata = (e: React.SyntheticEvent<HTMLVideoElement>) => {
    setDuration(e.currentTarget.duration);
  };

  return (
    <Card
      key={video.url}
      className="group relative cursor-pointer overflow-hidden rounded-[28px] border border-white/70 bg-white/82 shadow-[0_24px_60px_rgba(15,23,42,0.10)] transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_32px_90px_rgba(15,23,42,0.14)]"
      onClick={() => onSelect(video.isStatic ? video.url : video.file!)}
    >
      <div className="relative aspect-video overflow-hidden bg-slate-950">
        <video
          src={video.url}
          className="h-full w-full object-cover opacity-90 transition duration-500 group-hover:scale-[1.03] group-hover:opacity-100"
          muted
          onLoadedMetadata={handleLoadedMetadata}
          onMouseEnter={(e) => e.currentTarget.play()}
          onMouseLeave={(e) => {
            e.currentTarget.pause();
            e.currentTarget.currentTime = 0;
          }}
        />
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(8,15,34,0.10),rgba(8,15,34,0.58))]" />
        <div className="pointer-events-none absolute inset-x-5 top-5 flex items-center justify-between">
          <div className="rounded-full border border-white/20 bg-black/24 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-white/80 backdrop-blur-md">
            {video.isStatic ? "Sample clip" : "Custom clip"}
          </div>
          <div className="rounded-full border border-white/18 bg-white/14 p-3 text-white shadow-[0_12px_28px_rgba(0,0,0,0.22)] backdrop-blur-md transition-transform duration-300 group-hover:scale-110">
            <Play className="h-6 w-6 fill-white" />
          </div>
        </div>
      </div>
      <div className="bg-white/84 p-5 backdrop-blur-sm">
        <div className="mb-2 flex items-center justify-between gap-3">
          <p className="truncate text-lg font-bold tracking-tight text-slate-900">
            {video.name}
          </p>
          <div className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold  text-slate-500">
            {duration ? formatDuration(duration) : "0:00"}
          </div>
        </div>
        <p className="text-sm leading-6 text-slate-600">
          Open straight in the review editor with timeline controls and
          tracked-face overlays.
        </p>
      </div>
    </Card>
  );
}

export function Gallery({
  onSelect,
  onUserUpload,
  onImageFlowClick,
  userVideos,
}: GalleryProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const videoModules = import.meta.glob("../assets/video-projects/*.mp4", {
    eager: true,
    query: "?url",
    import: "default",
  });

  const staticVideos = Object.entries(videoModules).map(([path, url]) => ({
    name: path.split("/").pop()?.replace(".mp4", "") || "Video",
    url: url as string,
    file: null as File | null,
    isStatic: true,
  }));

  const allVideos = [
    ...staticVideos,
    ...userVideos.map((v) => ({ ...v, isStatic: false })),
  ].reverse();

  return (
    <div className="mx-auto w-full max-w-6xl px-2 pb-8">
      <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="text-3xl font-black tracking-tight text-slate-900">
            Your Video Projects
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Click here to open a file dialogue to upload a new tracking clip, or
            use a sample clip.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
        {allVideos.map((video) => (
          <GalleryVideoCard key={video.url} video={video} onSelect={onSelect} />
        ))}

        <div
          className="group relative min-h-[320px] cursor-pointer overflow-hidden rounded-[28px] border border-dashed border-slate-300 bg-[linear-gradient(135deg,rgba(255,255,255,0.7),rgba(244,247,255,0.9))] shadow-[0_20px_50px_rgba(15,23,42,0.06)] transition-all duration-300 hover:-translate-y-1 hover:border-slate-400 hover:shadow-[0_30px_90px_rgba(15,23,42,0.10)] md:min-h-[340px]"
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="video/mp4,video/quicktime,video/webm"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                onUserUpload(file);
                // Reset value so same file can be uploaded again if needed
                e.target.value = "";
              }
            }}
          />
          <div className="absolute -right-10 -top-10 h-32 w-32 rounded-full bg-lime-200/70 blur-3xl transition-transform duration-500 group-hover:scale-125" />
          <div className="absolute -bottom-12 left-8 h-32 w-32 rounded-full bg-sky-200/70 blur-3xl transition-transform duration-500 group-hover:scale-125" />
          <div className="relative flex h-full flex-col items-center justify-center gap-5 px-8 py-8 text-center md:px-10 md:py-10">
            <div className="rounded-full border border-slate-200 bg-white/88 p-5 text-slate-700 shadow-[0_12px_24px_rgba(15,23,42,0.08)] transition-all duration-300 group-hover:scale-105 group-hover:text-slate-950">
              <Upload className="h-8 w-8" />
            </div>
            <div className="max-w-[24rem]">
              <div className="text-lg font-bold tracking-tight text-slate-900">
                Upload New Video
              </div>
              <p className="mt-3 text-sm leading-7 text-slate-600">
                Bring your own clip into the live tracking pipeline and review
                it in the editor.
              </p>
            </div>
            <div className="rounded-full border border-slate-200 bg-white/88 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500 shadow-[0_8px_18px_rgba(15,23,42,0.05)]">
              MP4, MOV, WebM
            </div>
          </div>
        </div>

        <div
          onClick={onImageFlowClick}
          className="group relative min-h-[320px] cursor-pointer overflow-hidden rounded-[28px] border border-dashed border-slate-300 bg-[linear-gradient(135deg,rgba(255,255,255,0.7),rgba(244,247,255,0.9))] shadow-[0_20px_50px_rgba(15,23,42,0.06)] transition-all duration-300 hover:-translate-y-1 hover:border-slate-400 hover:shadow-[0_30px_90px_rgba(15,23,42,0.10)] md:min-h-[340px]"
        >
          <div className="absolute -right-10 -top-10 h-32 w-32 rounded-full bg-lime-200/70 blur-3xl transition-transform duration-500 group-hover:scale-125" />
          <div className="absolute -bottom-12 left-8 h-32 w-32 rounded-full bg-sky-200/70 blur-3xl transition-transform duration-500 group-hover:scale-125" />
          <div className="relative flex h-full flex-col items-center justify-center gap-5 px-8 py-8 text-center md:px-10 md:py-10">
            <div className="rounded-full border border-slate-200 bg-white/88 p-5 text-slate-700 shadow-[0_12px_24px_rgba(15,23,42,0.08)] transition-all duration-300 group-hover:scale-105 group-hover:text-slate-950">
              <ScanFace className="h-8 w-8" />
            </div>
            <div className="max-w-[24rem]">
              <div className="text-lg font-bold tracking-tight text-slate-900">
                Image Face Swap
              </div>
              <p className="mt-3 text-sm leading-7 text-slate-600">
                Upload a target image, review detected faces, and run the same
                backend swap pipeline without leaving the app.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
