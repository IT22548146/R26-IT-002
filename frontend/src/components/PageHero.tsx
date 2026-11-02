import Link from "next/link";
import { ChevronRight } from "lucide-react";

type Crumb = { name: string; href?: string };

const TONES: Record<string, { from: string; to: string; art: string; chip: string }> = {
  slate:   { from: "#0f172a", to: "#334155", art: "#64748b", chip: "text-slate-300" },
  blue:    { from: "#1e3a8a", to: "#2563eb", art: "#60a5fa", chip: "text-blue-200" },
  indigo:  { from: "#312e81", to: "#4f46e5", art: "#818cf8", chip: "text-indigo-200" },
  sky:     { from: "#0c4a6e", to: "#0ea5e9", art: "#38bdf8", chip: "text-sky-200" },
  emerald: { from: "#064e3b", to: "#059669", art: "#34d399", chip: "text-emerald-200" },
};

/**
 * Rounded, side-spaced breadcrumb hero used at the top of inner public pages.
 * The garment-motif artwork sits on the right; title + breadcrumb on the left.
 */
export default function PageHero({
  title,
  subtitle,
  crumbs = [],
  tone = "slate",
}: {
  title: string;
  subtitle?: string;
  crumbs?: Crumb[];
  tone?: keyof typeof TONES;
}) {
  const t = TONES[tone] ?? TONES.slate;
  const gid = `hero-${tone}`;

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 pt-6">
      <div className="relative overflow-hidden rounded-3xl">
        {/* Decorative garment-motif background (no text) */}
        <svg className="absolute inset-0 w-full h-full" viewBox="0 0 1200 340" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor={t.from} />
              <stop offset="1" stopColor={t.to} />
            </linearGradient>
          </defs>
          <rect width="1200" height="340" fill={`url(#${gid})`} />
          {/* soft blobs */}
          <circle cx="1040" cy="70" r="150" fill="#ffffff" opacity="0.06" />
          <circle cx="920" cy="300" r="120" fill="#ffffff" opacity="0.05" />
          {/* stitch dashes */}
          <path d="M760 60 C880 40 980 90 1160 60" stroke={t.art} strokeWidth="3" strokeDasharray="2 12" strokeLinecap="round" fill="none" opacity="0.7" />
          <path d="M700 300 C860 320 1000 270 1180 300" stroke={t.art} strokeWidth="3" strokeDasharray="2 12" strokeLinecap="round" fill="none" opacity="0.6" />
          {/* hanger + garment silhouette */}
          <g stroke={t.art} strokeWidth="4" fill="none" opacity="0.85" transform="translate(980 40)">
            <path d="M60 20 q0 -16 14 -16 q12 0 12 11" strokeLinecap="round" />
            <path d="M60 20 L14 56" strokeLinecap="round" />
            <path d="M60 20 L106 56" strokeLinecap="round" />
            <path d="M18 60 C40 52 80 52 102 60 C98 84 98 86 108 106 L108 210 q0 10 -10 10 L22 220 q-10 0 -10 -10 L12 106 C22 86 22 84 18 60 Z" opacity="0.9" />
          </g>
          {/* fabric swatch outlines */}
          <rect x="820" y="150" width="90" height="120" rx="16" stroke={t.art} strokeWidth="3" fill="#ffffff" fillOpacity="0.04" transform="rotate(-10 865 210)" />
        </svg>

        <div className="relative px-6 sm:px-10 py-12 sm:py-16">
          {/* breadcrumb */}
          <nav className="flex items-center gap-1 text-sm mb-4" aria-label="Breadcrumb">
            <Link href="/" className={`${t.chip} hover:text-white transition-colors`}>Home</Link>
            {crumbs.map((c) => (
              <span key={c.name} className="flex items-center gap-1">
                <ChevronRight className={`w-4 h-4 ${t.chip} opacity-60`} />
                {c.href ? (
                  <Link href={c.href} className={`${t.chip} hover:text-white transition-colors`}>{c.name}</Link>
                ) : (
                  <span className="text-white font-medium">{c.name}</span>
                )}
              </span>
            ))}
          </nav>
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white max-w-2xl">{title}</h1>
          {subtitle && <p className="mt-3 text-white/80 max-w-xl">{subtitle}</p>}
        </div>
      </div>
    </div>
  );
}
