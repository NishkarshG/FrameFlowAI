import { TriangleAlert, FlaskConical, Info, LoaderCircle, X } from "lucide-react";
import type { ReactNode } from "react";
import type { Severity } from "../types";
import { charColor, cls } from "../utils";

export function PageHeader({ title, subtitle, actions, eyebrow }: { title: string; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: string }) {
  return (
    <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div>
        {eyebrow && <div className="mb-1 text-xs font-semibold uppercase tracking-[0.14em] text-cyan-300/80">{eyebrow}</div>}
        <h1 className="font-display text-2xl font-semibold tracking-tight md:text-[28px]">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-white/55">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function SyntheticBadge({ className }: { className?: string }) {
  return (
    <span title="Fictional sample data created for demonstration — not real production data"
      className={cls("inline-flex items-center gap-1 rounded-full bg-amber-400/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-300 ring-1 ring-amber-300/30", className)}>
      <FlaskConical size={11} /> Synthetic
    </span>
  );
}

export function CharacterChip({ name, small }: { name: string; small?: boolean }) {
  const c = charColor(name);
  return (
    <span className={cls("inline-flex items-center rounded-md font-semibold tracking-wide ring-1", c.bg, c.text, c.ring, small ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-[11px]")}>
      {name}
    </span>
  );
}

const STATUS_STYLE = {
  good: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/25",
  warning: "bg-amber-400/10 text-amber-300 ring-amber-300/25",
  error: "bg-rose-500/10 text-rose-300 ring-rose-400/25",
} as const;

export function StatusBadge({ status, score }: { status: "good" | "warning" | "error"; score?: number }) {
  const label = status === "good" ? "Readable" : status === "warning" ? "Review" : "Fix needed";
  return (
    <span className={cls("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1", STATUS_STYLE[status])}>
      <span className={cls("h-1.5 w-1.5 rounded-full", status === "good" ? "bg-emerald-400" : status === "warning" ? "bg-amber-400" : "bg-rose-400")} />
      {label}{score !== undefined && <span className="opacity-70">· {score}</span>}
    </span>
  );
}

export function SeverityIcon({ severity }: { severity: Severity }) {
  if (severity === "info") return <Info size={14} className="mt-0.5 shrink-0 text-sky-300" />;
  return <TriangleAlert size={14} className={cls("mt-0.5 shrink-0", severity === "error" ? "text-rose-300" : "text-amber-300")} />;
}

export function Spinner({ size = 16 }: { size?: number }) {
  return <LoaderCircle size={size} className="animate-spin" />;
}

export function ErrorBanner({ title = "Something went wrong", message, onClose, children }: { title?: string; message: string; onClose?: () => void; children?: ReactNode }) {
  return (
    <div className="mb-5 flex gap-3 rounded-2xl border border-rose-500/25 bg-rose-500/[0.07] p-4 text-sm">
      <TriangleAlert className="mt-0.5 shrink-0 text-rose-300" size={18} />
      <div className="flex-1">
        <div className="font-semibold text-rose-200">{title}</div>
        <div className="mt-0.5 text-rose-100/80">{message}</div>
        {children}
      </div>
      {onClose && <button className="text-rose-200/60 hover:text-rose-100" onClick={onClose} aria-label="Dismiss"><X size={16} /></button>}
    </div>
  );
}

export function InfoBanner({ children, tone = "violet", icon }: { children: ReactNode; tone?: "violet" | "amber" | "cyan"; icon?: ReactNode }) {
  const tones = {
    violet: "border-violet-500/25 bg-violet-500/[0.07] text-violet-100/85",
    amber: "border-amber-400/25 bg-amber-400/[0.06] text-amber-100/85",
    cyan: "border-cyan-400/25 bg-cyan-400/[0.06] text-cyan-50/85",
  };
  return <div className={cls("mb-5 flex gap-3 rounded-2xl border p-4 text-sm", tones[tone])}>{icon ?? <Info size={18} className="mt-0.5 shrink-0" />}<div className="flex-1">{children}</div></div>;
}

export function EmptyState({ icon, title, body, action }: { icon: ReactNode; title: string; body: string; action?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center justify-center px-6 py-16 text-center">
      <div className="mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-violet-500/25 to-cyan-400/15 text-violet-200 ring-1 ring-white/10">{icon}</div>
      <h3 className="font-display text-lg font-semibold">{title}</h3>
      <p className="mt-1 max-w-md text-sm text-white/55">{body}</p>
      {action && <div className="mt-5 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}

export function StatCard({ icon, label, value, sub, accent = "violet" }: { icon: ReactNode; label: string; value: ReactNode; sub?: ReactNode; accent?: "violet" | "cyan" | "rose" | "emerald" }) {
  const acc = {
    violet: "from-violet-500/30 to-violet-500/0 text-violet-200",
    cyan: "from-cyan-400/25 to-cyan-400/0 text-cyan-200",
    rose: "from-rose-500/25 to-rose-500/0 text-rose-200",
    emerald: "from-emerald-400/25 to-emerald-400/0 text-emerald-200",
  }[accent];
  return (
    <div className="card relative overflow-hidden p-5">
      <div className={cls("pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full bg-gradient-to-br blur-2xl", acc)} />
      <div className="flex items-center justify-between">
        <span className="label">{label}</span>
        <span className={cls("grid h-8 w-8 place-items-center rounded-lg bg-white/[0.05] ring-1 ring-white/10", acc.split(" ").pop())}>{icon}</span>
      </div>
      <div className="mt-3 font-display text-3xl font-semibold tabular-nums tracking-tight">{value}</div>
      {sub && <div className="mt-1 text-xs text-white/50">{sub}</div>}
    </div>
  );
}

export function ScoreRing({ score, size = 64 }: { score: number | null; size?: number }) {
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const pct = score === null ? 0 : Math.max(0, Math.min(100, score)) / 100;
  return (
    <svg width={size} height={size} className="shrink-0">
      <defs>
        <linearGradient id="ring" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stopColor="#8B5CF6" /><stop offset="100%" stopColor="#22D3EE" /></linearGradient>
      </defs>
      <circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(255,255,255,0.08)" strokeWidth="6" fill="none" />
      <circle cx={size / 2} cy={size / 2} r={r} stroke="url(#ring)" strokeWidth="6" fill="none" strokeLinecap="round"
        strokeDasharray={`${c * pct} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" className="fill-white font-display text-[13px] font-semibold">
        {score === null ? "—" : Math.round(score)}
      </text>
    </svg>
  );
}

/** Grouped vertical bar chart (SVG, no dependencies). */
export function BarChart({ labels, series, height = 200 }: { labels: string[]; series: { name: string; color: string; values: number[] }[]; height?: number }) {
  const max = Math.max(1, ...series.flatMap((s) => s.values));
  const nice = max <= 5 ? Math.max(max, 1) : Math.ceil(max / 5) * 5;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => Math.round(nice * t * 10) / 10);
  const W = 640, H = height, padL = 32, padB = 26, padT = 8;
  const plotW = W - padL - 8, plotH = H - padB - padT;
  const groupW = plotW / labels.length;
  const barW = Math.max(2, Math.min(12, (groupW - 6) / series.length));
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Bar chart">
        {ticks.map((t) => {
          const y = padT + plotH - (t / nice) * plotH;
          return (
            <g key={t}>
              <line x1={padL} x2={W - 8} y1={y} y2={y} stroke="rgba(255,255,255,0.06)" />
              <text x={padL - 6} y={y} textAnchor="end" dominantBaseline="central" className="fill-white/35 text-[10px]">{t}</text>
            </g>
          );
        })}
        {labels.map((l, i) => {
          const gx = padL + i * groupW + (groupW - barW * series.length) / 2;
          return (
            <g key={l}>
              {series.map((s, k) => {
                const v = s.values[i] ?? 0;
                const h = (v / nice) * plotH;
                return (
                  <rect key={s.name} x={gx + k * barW} y={padT + plotH - h} width={barW - 1.5} height={Math.max(h, v > 0 ? 2 : 0)} rx={2} fill={s.color}>
                    <title>{`${l} · ${s.name}: ${v}`}</title>
                  </rect>
                );
              })}
              {(labels.length <= 14 ? i % 2 === 0 : i % 4 === 0) && (
                <text x={padL + i * groupW + groupW / 2} y={H - 8} textAnchor="middle" className="fill-white/40 text-[10px]">{l}</text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-4 text-xs text-white/60">
        {series.map((s) => (
          <span key={s.name} className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />{s.name}</span>
        ))}
      </div>
    </div>
  );
}

/** Horizontal bar list. */
export function HBarList({ items, color = "linear-gradient(90deg,#8B5CF6,#22D3EE)", empty = "No data yet." }: { items: { label: string; value: number; hint?: string }[]; color?: string; empty?: string }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  if (!items.length) return <div className="py-6 text-center text-sm text-white/40">{empty}</div>;
  return (
    <div className="space-y-3">
      {items.map((i) => (
        <div key={i.label}>
          <div className="mb-1 flex justify-between text-xs"><span className="text-white/75">{i.label}</span><span className="tabular-nums text-white/50">{i.value}</span></div>
          <div className="h-2 overflow-hidden rounded-full bg-white/[0.05]">
            <div className="h-full rounded-full" style={{ width: `${(i.value / max) * 100}%`, background: color }} title={i.hint} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function Toast({ message, tone, onClose }: { message: string; tone: "success" | "error" | "info"; onClose: () => void }) {
  const t = { success: "border-emerald-400/30 text-emerald-100", error: "border-rose-400/30 text-rose-100", info: "border-violet-400/30 text-violet-100" }[tone];
  return (
    <div className={cls("fixed bottom-5 right-5 z-50 flex max-w-md items-start gap-3 rounded-xl border bg-panel/95 px-4 py-3 text-sm shadow-2xl backdrop-blur", t)}>
      <span className="flex-1">{message}</span>
      <button onClick={onClose} className="opacity-60 hover:opacity-100" aria-label="Dismiss"><X size={15} /></button>
    </div>
  );
}
