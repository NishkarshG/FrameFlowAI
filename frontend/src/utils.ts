export function fmtTime(ms: number | null | undefined, short = false): string {
  if (ms === null || ms === undefined) return short ? "--:--" : "--:--:--,---";
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  const s = Math.floor((ms % 60_000) / 1000);
  const r = ms % 1000;
  const p = (n: number, w = 2) => String(n).padStart(w, "0");
  if (short) return `${h ? p(h) + ":" : ""}${p(m)}:${p(s)}.${p(Math.floor(r / 100), 1)}`;
  return `${p(h)}:${p(m)}:${p(s)},${p(r, 3)}`;
}

/** Client-side mirror of the backend parser (for live previews only; the backend validates). */
export function parseTime(v: string): number | null | undefined {
  const s = v.trim();
  if (!s) return null;
  const m = /^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?$/.exec(s);
  if (!m) return undefined; // invalid
  const [, h, mi, se, ms] = m;
  if (Number(mi) >= 60 || Number(se) >= 60) return undefined;
  return ((Number(h ?? 0) * 60 + Number(mi)) * 60 + Number(se)) * 1000 + Number((ms ?? "0").padEnd(3, "0").slice(0, 3));
}

const CHAR_COLORS = [
  { text: "text-violet-300", bg: "bg-violet-500/15", ring: "ring-violet-400/30", hex: "#a78bfa" },
  { text: "text-cyan-300", bg: "bg-cyan-400/15", ring: "ring-cyan-400/30", hex: "#67e8f9" },
  { text: "text-pink-300", bg: "bg-pink-500/15", ring: "ring-pink-400/30", hex: "#f9a8d4" },
  { text: "text-amber-200", bg: "bg-amber-400/15", ring: "ring-amber-300/30", hex: "#fde68a" },
  { text: "text-emerald-300", bg: "bg-emerald-400/15", ring: "ring-emerald-400/30", hex: "#6ee7b7" },
  { text: "text-sky-300", bg: "bg-sky-400/15", ring: "ring-sky-400/30", hex: "#7dd3fc" },
];

export function charColor(name: string) {
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return CHAR_COLORS[h % CHAR_COLORS.length];
}

export const ISSUE_LABELS: Record<string, string> = {
  too_many_chars: "Too many characters",
  long_line: "Long line",
  too_many_lines: "Too many lines",
  reading_speed: "Reading speed",
  too_short: "Too short on screen",
  too_long_duration: "Too long on screen",
  overlap: "Timestamp overlap",
  missing_timing: "Missing timing",
  invalid_timing: "Invalid timing",
  empty_text: "Empty segment",
  difficult_words: "Difficult words",
  long_sentence: "Long sentence",
};

export const TIMING_LABELS: Record<string, string> = {
  original: "From screenplay",
  derived_split: "Split of original cue",
  manual: "Manual",
  missing: "Missing — enter manually",
};

export function cls(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

export function scoreColor(score: number | null | undefined) {
  if (score === null || score === undefined) return "text-white/40";
  if (score >= 90) return "text-emerald-300";
  if (score >= 75) return "text-cyan-300";
  if (score >= 50) return "text-amber-300";
  return "text-rose-300";
}

export function relTime(iso: string) {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
