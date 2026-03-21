import { useCallback, useRef, useState } from "react";
import { Upload } from "lucide-react";

interface VideoUploaderProps {
  onUpload: (file: File) => void;
  isUploading: boolean;
}

export function VideoUploader({ onUpload, isUploading }: VideoUploaderProps) {
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((file: File) => {
    const validTypes = ["video/mp4", "video/quicktime", "video/webm"];
    if (!validTypes.includes(file.type)) {
      alert("Please upload an MP4, MOV, or WebM file.");
      return;
    }
    setSelectedFile(file);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  return (
    <div className="flex flex-col items-center gap-6 w-full max-w-lg">
      <div
        className={`w-full border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-colors ${
          dragOver
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25 hover:border-primary/50"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept="video/mp4,video/quicktime,video/webm"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
        <Upload className="w-10 h-10 mx-auto mb-4 text-muted-foreground" />
        <p className="text-lg font-medium">Drop a video here</p>
        <p className="text-sm text-muted-foreground mt-1">
          or click to browse (MP4, MOV, WebM)
        </p>
      </div>

      {selectedFile && (
        <div className="flex flex-col items-center gap-3 w-full">
          <p className="text-sm text-muted-foreground truncate max-w-full">
            {selectedFile.name} (
            {(selectedFile.size / 1024 / 1024).toFixed(1)} MB)
          </p>
          <button
            className="w-full py-3 px-6 bg-primary text-primary-foreground rounded-xl font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
            onClick={() => onUpload(selectedFile)}
            disabled={isUploading}
          >
            {isUploading ? "Uploading..." : "Upload & Analyze"}
          </button>
        </div>
      )}
    </div>
  );
}
