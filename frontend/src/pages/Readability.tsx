import { OctagonAlert, TriangleAlert, ChevronDown, Info, SlidersHorizontal } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../api";
import { RequireEpisode } from "../components/RequireEpisode";
import { ThresholdForm } from "../components/ThresholdForm";
import { CharacterChip, HBarList, InfoBanner, PageHeader, ScoreRing, SeverityIcon, StatCard, StatusBadge } from "../components/ui";
import { useApp } from "../context";
import type { Episode, Thresholds } from "../types";
import { cls, fmtTime, ISSUE_LABELS } from "../utils";

function Meter({ value, limit, unit }: { value: number | null; limit: number; unit: string }) {
  if (value === null) return <span className="text-white/30">—</span>;
  const pct = Math.min(100, (value / (limit * 1.5)) * 100);
  const over = value > limit;
  return (
    <div className="w-20">
      <div className={cls("text-xs tabular-nums", over ? "text-amber-300" : "text-white/75")}>{unit === "" ? Math.round(value) : value.toFixed(unit === "s" ? 2 : 1)}{unit}</div>
      <div className="relative mt-1 h-1.5 rounded-full bg-white/[0.06]">
        <div className={cls("h-full rounded-full", over ? "bg-gradient-to-r from-amber-400 to-rose-400" : "bg-gradient-to-r from-violet-500 to-cyan-400")} style={{ width: `${pct}%` }} />
        <div className="absolute top-[-2px] h-2.5 w-px bg-white/50" style={{ left: `${(1 / 1.5) * 100}%` }} title={`Guideline ${limit}${unit}`} />
      </div>
    </div>
  );
}

function Body({ ep }: { ep: Episode }) {
  const { go, settings, setSettings, selectEpisode, notify } = useApp();
  const [severity, setSeverity] = useState<"all" | "error" | "warning" | "info">("all");
  const [code, setCode] = useState("all");
  const [showTh, setShowTh] = useState(false);
  const [saving, setSaving] = useState(false);
  const rep = ep.report;
  const counts = useMemo(() => {
    const all = Object.values(rep.segments).flatMap((r) => r.issues);
    return { info: all.filter((i) => i.severity === "info").length };
  }, [rep]);

  const rows = ep.segments.filter((s) => {
    const r = rep.segments[s.id];
    if (severity !== "all" && !r.issues.some((i) => i.severity === severity)) return false;
    if (code !== "all" && !r.issues.some((i) => i.code === code)) return false;
    return true;
  });

  const saveTh = async (t: Thresholds) => {
    setSaving(true);
    try {
      setSettings(await api.saveSettings({ thresholds: t }));
      selectEpisode(ep.id);
      notify("Thresholds saved — checks recalculated.");
    } catch (e) { notify((e as Error).message, "error"); }
    finally { setSaving(false); }
  };

  const th = ep.thresholds;
  return (
    <>
      <PageHeader eyebrow={ep.project_name} title="Readability Intelligence"
        subtitle={`${ep.name} · deterministic checks for line length, characters per card, reading speed, duration, overlaps, empty segments and potentially difficult language.`}
        actions={<button className="btn-ghost" onClick={() => setShowTh(!showTh)}><SlidersHorizontal size={15} /> Thresholds <ChevronDown size={14} className={cls("transition-transform", showTh && "rotate-180")} /></button>} />

      <InfoBanner>
        <div className="font-semibold text-white">Editorial guidelines, not universal standards</div>
        <div className="mt-0.5">{rep.disclaimer}</div>
      </InfoBanner>

      {showTh && settings && (
        <div className="card mb-5 p-5">
          <h3 className="mb-4 font-display font-semibold">Editorial thresholds</h3>
          <ThresholdForm value={settings.thresholds} onSave={(t) => void saveTh(t)} saving={saving} />
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="card flex items-center gap-4 p-5">
          <ScoreRing score={rep.average_score} size={72} />
          <div><div className="label">Episode score</div><div className="mt-1 text-xs text-white/50">Average of {rep.total_segments} cards. Errors −25, warnings −10, info −4.</div></div>
        </div>
        <StatCard icon={<OctagonAlert size={16} />} accent="rose" label="Errors" value={rep.error_count} sub="Must fix before delivery" />
        <StatCard icon={<TriangleAlert size={16} />} accent="violet" label="Warnings" value={rep.warning_count} sub="Worth an editorial look" />
        <StatCard icon={<Info size={16} />} accent="cyan" label="Language notes" value={counts.info} sub="Potentially difficult wording" />
      </div>

      <div className="mt-4 grid gap-4 2xl:grid-cols-[1fr_320px]">
        <div className="card min-w-0 overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 px-5 pt-5">
            <h3 className="mr-auto font-display font-semibold">Card-by-card analysis</h3>
            <select className="input w-auto py-1.5 text-xs" value={severity} onChange={(e) => setSeverity(e.target.value as typeof severity)} aria-label="Severity">
              <option value="all">All severities</option><option value="error">Errors</option><option value="warning">Warnings</option><option value="info">Info</option>
            </select>
            <select className="input w-auto py-1.5 text-xs" value={code} onChange={(e) => setCode(e.target.value)} aria-label="Issue type">
              <option value="all">All issue types</option>
              {Object.keys(rep.issue_breakdown).map((c) => <option key={c} value={c}>{ISSUE_LABELS[c] ?? c}</option>)}
            </select>
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-white/40">
                  <th className="py-2 pl-5 pr-2 font-medium">#</th><th className="px-2 py-2 font-medium">Subtitle</th>
                  <th className="px-2 py-2 font-medium">Chars</th><th className="px-2 py-2 font-medium">Duration</th>
                  <th className="px-2 py-2 font-medium">Reading speed</th><th className="px-2 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((s) => {
                  const r = rep.segments[s.id];
                  return (
                    <tr key={s.id} className="cursor-pointer border-t border-white/[0.05] align-top hover:bg-white/[0.02]" onClick={() => go("editor", s.id)} title="Open in editor">
                      <td className="py-3 pl-5 pr-2 font-mono text-xs text-white/40">{s.index + 1}</td>
                      <td className="px-2 py-3">
                        <div className="flex items-center gap-2"><CharacterChip name={s.character} small /><span className="font-mono text-[11px] text-white/40">{fmtTime(s.start_ms, true)} → {fmtTime(s.end_ms, true)}</span></div>
                        <div className="mt-1 text-white/85">{s.text || <i className="text-white/30">(empty)</i>}</div>
                        {r.issues.length > 0 && (
                          <ul className="mt-1.5 space-y-0.5">{r.issues.map((i, k) => <li key={k} className="flex gap-1.5 text-[11px] text-white/55"><SeverityIcon severity={i.severity} />{i.message}</li>)}</ul>
                        )}
                      </td>
                      <td className="px-2 py-3"><Meter value={r.metrics.chars} limit={th.max_chars_per_segment} unit="" /><div className="mt-1 text-[10px] text-white/35">{r.metrics.line_count} line(s), longest {r.metrics.longest_line}</div></td>
                      <td className="px-2 py-3"><Meter value={r.metrics.duration_s} limit={th.max_duration_s} unit="s" /></td>
                      <td className="px-2 py-3"><Meter value={r.metrics.cps} limit={th.max_cps} unit=" cps" /></td>
                      <td className="py-3 pl-2 pr-5"><StatusBadge status={r.status} score={r.score} /></td>
                    </tr>
                  );
                })}
                {rows.length === 0 && <tr><td colSpan={6} className="px-5 py-10 text-center text-white/40">No cards match this filter.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
        <div className="space-y-4">
          <div className="card p-5">
            <h3 className="mb-4 font-display font-semibold">Issues by type</h3>
            <HBarList items={Object.entries(rep.issue_breakdown).map(([k, v]) => ({ label: ISSUE_LABELS[k] ?? k, value: v }))} empty="No issues 🎬" />
          </div>
          <div className="card p-5 text-xs leading-6 text-white/60">
            <h3 className="mb-2 font-display text-sm font-semibold text-white">How these are measured</h3>
            <p><b className="text-white/80">Reading speed</b> = characters (incl. spaces) ÷ seconds on screen.</p>
            <p><b className="text-white/80">Lines</b> are wrapped at {th.max_chars_per_line} chars, balanced for two-line cards.</p>
            <p><b className="text-white/80">Overlap</b> = a card starts before the previous card ends.</p>
            <p><b className="text-white/80">Difficult words</b> = ≥{th.long_word_chars} letters or ≥5 syllables (heuristic).</p>
            <p className="mt-2 text-white/40">All checks run locally in Python — they never depend on the AI service.</p>
          </div>
        </div>
      </div>
    </>
  );
}

export default function Readability() {
  return <RequireEpisode>{(ep) => <Body ep={ep} />}</RequireEpisode>;
}
