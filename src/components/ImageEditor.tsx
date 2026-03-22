import { useState, useRef } from "react";
import { ArrowLeft, Upload, Image as ImageIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";

export function ImageEditor() {
  const navigate = useNavigate();
  const [referenceImg, setReferenceImg] = useState<string | null>(null);
  const [inspirationImg, setInspirationImg] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");

  const refInputRef = useRef<HTMLInputElement>(null);
  const insInputRef = useRef<HTMLInputElement>(null);

  const handleImageUpload = (
    e: React.ChangeEvent<HTMLInputElement>,
    setter: React.Dispatch<React.SetStateAction<string | null>>,
  ) => {
    const file = e.target.files?.[0];
    if (file) {
      const url = URL.createObjectURL(file);
      setter(url);
    }
  };

  return (
    <div className="w-full max-w-4xl rounded-[32px] border border-white/70 bg-white/70 p-6 shadow-[0_30px_90px_rgba(15,23,42,0.10)] backdrop-blur-xl md:p-10">
      <div className="mb-8 flex items-center justify-between">
        <button
          onClick={() => navigate("/")}
          className="flex items-center gap-2 rounded-full border border-black/8 bg-white/80 px-4 py-2 text-sm font-medium text-slate-600 transition-colors hover:text-slate-950"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Gallery
        </button>
      </div>

      <div className="mb-6">
        <h2 className="text-3xl font-black tracking-tight text-slate-900">
          Avatar Studio
        </h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Upload a reference face and an inspiration image to generate your own
          custom AI avatar.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
        {/* Reference Image */}
        <div className="flex flex-col gap-3">
          <label className="text-sm font-bold text-slate-900">
            Reference Picture (Face)
          </label>
          <div
            className="group relative flex aspect-square cursor-pointer flex-col items-center justify-center overflow-hidden rounded-[24px] border-2 border-dashed border-slate-300 bg-white/50 transition-all hover:border-slate-400"
            onClick={() => refInputRef.current?.click()}
          >
            <input
              ref={refInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => handleImageUpload(e, setReferenceImg)}
            />
            {referenceImg ? (
              <img
                src={referenceImg}
                alt="Reference"
                className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
              />
            ) : (
              <div className="flex flex-col items-center gap-3 p-6 text-center text-slate-500 group-hover:text-slate-700">
                <Upload className="h-8 w-8" />
                <span className="text-sm font-medium">Upload Reference</span>
              </div>
            )}
            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/50 to-transparent p-4 opacity-0 transition-opacity duration-300 group-hover:opacity-100">
              <p className="text-center text-xs font-medium text-white shadow-sm">
                Click to change image
              </p>
            </div>
          </div>
        </div>

        {/* Inspiration Image */}
        <div className="flex flex-col gap-3">
          <label className="text-sm font-bold text-slate-900">
            Inspiration Picture (Style)
          </label>
          <div
            className="group relative flex aspect-square cursor-pointer flex-col items-center justify-center overflow-hidden rounded-[24px] border-2 border-dashed border-slate-300 bg-[linear-gradient(135deg,rgba(255,255,255,0.7),rgba(244,247,255,0.9))] transition-all hover:border-slate-400"
            onClick={() => insInputRef.current?.click()}
          >
            <input
              ref={insInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => handleImageUpload(e, setInspirationImg)}
            />
            {inspirationImg ? (
              <img
                src={inspirationImg}
                alt="Inspiration"
                className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
              />
            ) : (
              <div className="flex flex-col items-center gap-3 p-6 text-center text-slate-500 group-hover:text-slate-700">
                <ImageIcon className="h-8 w-8" />
                <span className="text-sm font-medium">Upload Style</span>
              </div>
            )}
            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/50 to-transparent p-4 opacity-0 transition-opacity duration-300 group-hover:opacity-100">
              <p className="text-center text-xs font-medium text-white shadow-sm">
                Click to change image
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-8 flex flex-col gap-3">
        <label className="text-sm font-bold text-slate-900">
          Additional Prompt Context
        </label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="e.g., Make it look like a futuristic cyberpunk character..."
          className="min-h-[100px] w-full resize-y rounded-[20px] border border-slate-200 bg-white/80 p-5 text-sm outline-none transition-all placeholder:text-slate-400 focus:border-slate-400 focus:ring-4 focus:ring-slate-100"
        />
      </div>

      <div className="mt-8 flex justify-end">
        <button
          disabled={!referenceImg || !inspirationImg}
          className="rounded-full bg-[linear-gradient(135deg,#111827_0%,#2b344f_100%)] px-8 py-3.5 font-bold text-white shadow-[0_12px_24px_rgba(15,23,42,0.16)] transition-all hover:-translate-y-0.5 hover:shadow-[0_16px_32px_rgba(15,23,42,0.2)] disabled:pointer-events-none disabled:opacity-50"
        >
          Generate Avatar
        </button>
      </div>
    </div>
  );
}
