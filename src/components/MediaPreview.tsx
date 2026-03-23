import type { MediaType } from "../types";

interface MediaPreviewProps {
  src: string;
  mediaType?: MediaType | null;
  className?: string;
  alt?: string;
}

export function MediaPreview({
  src,
  mediaType = "video",
  className = "",
  alt = "Generated media preview",
}: MediaPreviewProps) {
  if (mediaType === "image") {
    return (
      <img
        src={src}
        alt={alt}
        className={`w-full rounded-xl bg-black object-contain max-h-[400px] ${className}`}
      />
    );
  }

  return (
    <video
      src={src}
      controls
      className={`w-full rounded-xl bg-black object-contain max-h-[400px] ${className}`}
    />
  );
}
