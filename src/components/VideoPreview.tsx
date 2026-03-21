interface VideoPreviewProps {
  src: string;
  className?: string;
}

export function VideoPreview({ src, className = "" }: VideoPreviewProps) {
  return (
    <video
      src={src}
      controls
      className={`w-full rounded-xl bg-black object-contain max-h-[400px] ${className}`}
    />
  );
}
