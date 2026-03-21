import { Card } from "./ui/card";
import { Upload, Play } from "lucide-react";
import { Button } from "./ui/button";

interface GalleryProps {
  onSelect: (src: string) => void;
  onUploadClick: () => void;
}

export function Gallery({ onSelect, onUploadClick }: GalleryProps) {
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
    <div className="mx-auto w-full max-w-6xl px-2 pb-8">
      <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">
            Launch A Project
          </div>
          <h2 className="text-3xl font-black tracking-tight text-slate-900">
            Your Video Projects
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            Open a sample clip to explore the editor instantly, or upload your own
            footage and run the live tracking flow.
          </p>
        </div>
        <Button
          onClick={onUploadClick}
          className="gap-2 rounded-full bg-slate-950 px-5 text-white shadow-[0_18px_36px_rgba(15,23,42,0.16)] hover:bg-slate-900"
        >
          <Upload className="w-4 h-4" />
          Upload New
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
        {videos.map((video) => (
          <Card
            key={video.path}
            className="group relative cursor-pointer overflow-hidden rounded-[28px] border border-white/70 bg-white/82 shadow-[0_24px_60px_rgba(15,23,42,0.10)] transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_32px_90px_rgba(15,23,42,0.14)]"
            onClick={() => onSelect(video.url)}
          >
            <div className="relative aspect-video overflow-hidden bg-slate-950">
              <video
                src={video.url}
                className="h-full w-full object-cover opacity-90 transition duration-500 group-hover:scale-[1.03] group-hover:opacity-100"
                muted
                onMouseEnter={(e) => e.currentTarget.play()}
                onMouseLeave={(e) => {
                  e.currentTarget.pause();
                  e.currentTarget.currentTime = 0;
                }}
              />
              <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(8,15,34,0.10),rgba(8,15,34,0.58))]" />
              <div className="pointer-events-none absolute inset-x-5 top-5 flex items-center justify-between">
                <div className="rounded-full border border-white/20 bg-black/24 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-white/80 backdrop-blur-md">
                  Sample clip
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
                <div className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                  Ready
                </div>
              </div>
              <p className="text-sm leading-6 text-slate-600">
                Open straight in the review editor with timeline controls and
                tracked-face overlays.
              </p>
              <div className="mt-4 text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">
                Demo Project
              </div>
            </div>
          </Card>
        ))}

        <div
          className="group relative min-h-[320px] cursor-pointer overflow-hidden rounded-[28px] border border-dashed border-slate-300 bg-[linear-gradient(135deg,rgba(255,255,255,0.7),rgba(244,247,255,0.9))] shadow-[0_20px_50px_rgba(15,23,42,0.06)] transition-all duration-300 hover:-translate-y-1 hover:border-slate-400 hover:shadow-[0_30px_90px_rgba(15,23,42,0.10)] md:min-h-[340px]"
          onClick={onUploadClick}
        >
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
                Bring your own clip into the live tracking pipeline and review it
                in the editor.
              </p>
            </div>
            <div className="rounded-full border border-slate-200 bg-white/88 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500 shadow-[0_8px_18px_rgba(15,23,42,0.05)]">
              MP4, MOV, WebM
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
