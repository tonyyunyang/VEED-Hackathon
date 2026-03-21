import veedLogo from "../assets/brand/veed.png";
import lovableLogo from "../assets/brand/lovable.png";
import runwareLogo from "../assets/brand/runware.png";

interface PartnerStripProps {
  compact?: boolean;
  className?: string;
}

interface PartnerBadgeProps {
  accent: string;
  compact?: boolean;
  label: string;
  logoSrc: string;
  name: string;
}

const PARTNERS = [
  {
    label: "Hosted by",
    name: "VEED",
    logoSrc: veedLogo,
    accent:
      "radial-gradient(circle at top left, rgba(161,255,116,0.34), rgba(161,255,116,0) 60%)",
  },
  {
    label: "Supported by",
    name: "Lovable",
    logoSrc: lovableLogo,
    accent:
      "radial-gradient(circle at top left, rgba(255,142,87,0.26), rgba(255,142,87,0) 60%)",
  },
  {
    label: "Supported by",
    name: "Runware",
    logoSrc: runwareLogo,
    accent:
      "radial-gradient(circle at top left, rgba(122,87,255,0.24), rgba(122,87,255,0) 60%)",
  },
];

function PartnerBadge({
  accent,
  compact = false,
  label,
  logoSrc,
  name,
}: PartnerBadgeProps) {
  const logoSize = compact ? "h-10 w-10" : "h-12 w-12";

  return (
    <div
      className={`group relative overflow-hidden rounded-[28px] border border-black/8 bg-white/74 shadow-[0_20px_50px_rgba(15,23,42,0.08)] backdrop-blur-xl transition-transform duration-300 hover:-translate-y-0.5 ${
        compact ? "px-3 py-2.5" : "px-4 py-3.5"
      }`}
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-90"
        style={{ backgroundImage: accent }}
      />
      <div className="relative flex items-center gap-3">
        <div
          className={`flex shrink-0 items-center justify-center rounded-[20px] border border-black/6 bg-white/92 p-2 shadow-[0_14px_28px_rgba(255,255,255,0.8)] ${logoSize}`}
        >
          <img
            src={logoSrc}
            alt={`${name} logo`}
            className="h-full w-full object-contain"
          />
        </div>
        <div className="min-w-0">
          <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
            {label}
          </div>
          <div
            className={`truncate font-semibold tracking-tight text-slate-900 ${
              compact ? "text-sm" : "text-base"
            }`}
          >
            {name}
          </div>
        </div>
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
      {PARTNERS.map((partner) => (
        <PartnerBadge
          key={partner.name}
          accent={partner.accent}
          compact={compact}
          label={partner.label}
          logoSrc={partner.logoSrc}
          name={partner.name}
        />
      ))}
    </div>
  );
}
