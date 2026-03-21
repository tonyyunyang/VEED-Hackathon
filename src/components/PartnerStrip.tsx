import type { ReactNode } from "react";

interface PartnerStripProps {
  compact?: boolean;
  className?: string;
}

interface LogoProps {
  compact?: boolean;
}

function VeedLogo({ compact = false }: LogoProps) {
  return (
    <div
      className={`inline-flex items-center justify-center overflow-hidden rounded-[28px] border border-lime-200/65 bg-[linear-gradient(135deg,#9fff7b_0%,#b7ff80_46%,#95ffbd_100%)] text-slate-950 shadow-[0_18px_36px_rgba(156,255,116,0.28)] ${
        compact ? "h-11 px-4" : "h-14 px-5"
      }`}
    >
      <span
        className={`font-black tracking-[0.24em] text-slate-950 ${
          compact ? "text-sm" : "text-base"
        }`}
      >
        VEED
      </span>
    </div>
  );
}

function LovableLogo({ compact = false }: LogoProps) {
  const size = compact ? 34 : 40;

  return (
    <div
      className="inline-flex items-center justify-center rounded-[24px] shadow-[0_18px_36px_rgba(255,92,139,0.22)]"
      style={{ width: size, height: size }}
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 64 64"
        fill="none"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id="lovableGradient" x1="6" y1="8" x2="58" y2="58">
            <stop offset="0%" stopColor="#ff8a00" />
            <stop offset="35%" stopColor="#ff4f6f" />
            <stop offset="70%" stopColor="#b660ff" />
            <stop offset="100%" stopColor="#4c78ff" />
          </linearGradient>
        </defs>
        <path
          d="M20 10C28.5 10 34 15.7 34 23.8C34 15.7 39.5 10 48 10C57.9 10 64 17.2 64 26.9C64 42.9 49.6 54 34 54C18.4 54 4 42.9 4 26.9C4 17.2 10.1 10 20 10Z"
          fill="url(#lovableGradient)"
        />
      </svg>
    </div>
  );
}

function RunwareLogo({ compact = false }: LogoProps) {
  const size = compact ? 34 : 40;

  return (
    <div
      className="inline-flex items-center justify-center rounded-[20px] shadow-[0_18px_36px_rgba(120,86,255,0.22)]"
      style={{ width: size, height: size }}
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 64 64"
        fill="none"
        aria-hidden="true"
      >
        <rect width="64" height="64" rx="18" fill="#7A57FF" />
        <path
          d="M19 18H44L50 32L44 46L50 58H39L34 47L25 47L20 36H31L35 44H39L35 36L41 26L38 18H19Z"
          fill="white"
        />
      </svg>
    </div>
  );
}

function PartnerBadge({
  label,
  logo,
  name,
  compact = false,
}: {
  label: string;
  logo: ReactNode;
  name: string;
  compact?: boolean;
}) {
  return (
    <div
      className={`flex items-center gap-3 rounded-[26px] border border-white/12 bg-[linear-gradient(180deg,rgba(255,255,255,0.1),rgba(255,255,255,0.04))] shadow-[0_24px_60px_rgba(15,23,42,0.18)] backdrop-blur-xl ${
        compact ? "px-3 py-2" : "px-4 py-3"
      }`}
    >
      {logo}
      <div className="flex flex-col">
        <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-white/45">
          {label}
        </span>
        <span className={`font-semibold tracking-tight text-white ${compact ? "text-sm" : "text-base"}`}>
          {name}
        </span>
      </div>
    </div>
  );
}

export function PartnerStrip({
  compact = false,
  className = "",
}: PartnerStripProps) {
  return (
    <div className={`flex flex-wrap items-center gap-3 ${className}`}>
      <PartnerBadge
        label="Hosted by"
        name="VEED"
        logo={<VeedLogo compact={compact} />}
        compact={compact}
      />
      <PartnerBadge
        label="Supported by"
        name="Lovable"
        logo={<LovableLogo compact={compact} />}
        compact={compact}
      />
      <PartnerBadge
        label="Supported by"
        name="Runware"
        logo={<RunwareLogo compact={compact} />}
        compact={compact}
      />
    </div>
  );
}
