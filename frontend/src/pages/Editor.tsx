import { TriangleAlert, ChevronDown, Clock, RotateCcw, Save, Scissors, Search, Sparkles, Undo2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { RequireEpisode } from "../components/RequireEpisode";
import { CharacterChip, ErrorBanner, PageHeader, SeverityIcon, Spinner, StatusBadge, SyntheticBadge } from "../components/ui";
import { useApp } from "../context";
import type { Episode, Segment, SegmentReport } from "../types";
import { cls, fmtTime, parseTime, TIMING_LABELS } from "../utils";

function SegmentCard({ ep, seg, rep, focused }: { ep: Episode; seg: Segment; rep: SegmentReport; focused: boolean }) {
  const { setEpisode, notify } = useApp();
  const [text, setText] = useState(seg.text);
  const [start, setStart] = useState(seg.start_ms === null ? "" : fmtTime(seg.start_ms));
  const [end, setEnd] = useState(seg.end_ms === null ? "" : fmtTime(seg.end_ms));
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setText(seg.text);
    setStart(seg.start_ms === null ? "" : fmtTime(seg.start_ms));
    setEnd(seg.end_ms === null ? "" : fmtTime(seg.end_ms));
  }, [seg.text, seg.start_ms, seg.end_ms]);
  useEffect(() => { if (focused) ref.current?.scrollIntoView({ behavior: "smooth", block: "center" }); }, [focused]);

  const origStart = seg.start_ms === null ? "" : fmtTime(seg.start_ms);
  const origEnd = seg.end_ms === null ? "" : fmtTime(seg.end_ms);
  const dirty = text !== seg.text || start !== origStart || end !== origEnd;
  const sMs = parseTime(start), eMs = parseTime(end);
  const timeInvalid = sMs === undefined || eMs === undefined;
  const liveDur = typeof sMs === "number" && typeof eMs === "number" && eMs > sMs ? (eMs - sMs) / 1000 : null;
  const liveCps = liveDur ? text.length / liveDur : null;
  const th = ep.thresholds;

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      const body: { text?: string; start?: string; end?: string } = {};
      if (text !== seg.text) body.text = text;
      if (start !== origStart) body.start = start;
      if (end !== origEnd) body.end = end;
      setEpisode(await api.updateSegment(ep.id, seg.id, body));
      notify(`Segment #${seg.index + 1} saved.`);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  };
  const revert = () => { setText(seg.text); setStart(origStart); setEnd(origEnd); setErr(null); };

  return (
    <div ref={ref} className={cls("card p-4 transition-shadow", focused && "ring-2 ring-cyan-400/50",
      rep.status === "error" ? "border-l-2 border-l-rose-400/70" : rep.status === "warning" ? "border-l-2 border-l-amber-400/60" : "border-l-2 border-l-emerald-400/50")}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-white/35">#{String(seg.index + 1).padStart(2, "0")}</span>
        <CharacterChip name={seg.character} />
        {seg.parenthetical && <span className="text-xs italic text-white/45">({seg.parenthetical})</span>}
        <StatusBadge status={rep.status} score={rep.score} />
        {seg.split_method === "ai" && <span className="rounded-full bg-violet-500/10 px-2 py-0.5 text-[10px] text-violet-200 ring-1 ring-violet-400/25">AI split</span>}
        {seg.edited && <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] text-white/60">edited</span>}
        <span className="ml-auto text-[11px] text-white/35">screenplay line {seg.source_line}</span>
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-[1fr_250px]">
        <div>
          <textarea className="input min-h-[72px] resize-y text-[15px] leading-relaxed" value={text} onChange={(e) => setText(e.target.value)} aria-label="Subtitle text" />
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-white/45">
            <span className={text.length > th.max_chars_per_segment ? "text-rose-300" : ""}>{text.length}/{th.max_chars_per_segment} chars</span>
            <span>{rep.metrics.line_count} line{rep.metrics.line_count === 1 ? "" : "s"} on screen</span>
            <span className={liveCps && liveCps > th.max_cps ? "text-amber-300" : ""}>{liveCps ? `${liveCps.toFixed(1)} cps` : "cps —"}</span>
            {seg.text !== seg.original_text && <span title={seg.original_text} className="text-violet-300/80">original: “{seg.original_text.slice(0, 50)}{seg.original_text.length > 50 ? "…" : ""}”</span>}
          </div>
        </div>
        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <label><span className="label">Start</span>
              <input className={cls("input mt-1 px-2 py-1.5 font-mono text-xs", sMs === undefined && "border-rose-400/60")} value={start} placeholder="HH:MM:SS,mmm" onChange={(e) => setStart(e.target.value)} /></label>
            <label><span className="label">End</span>
              <input className={cls("input mt-1 px-2 py-1.5 font-mono text-xs", eMs === undefined && "border-rose-400/60")} value={end} placeholder="HH:MM:SS,mmm" onChange={(e) => setEnd(e.target.value)} /></label>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-white/45">
            <Clock size={12} /> {liveDur ? `${liveDur.toFixed(2)}s` : "duration —"} ·
            <span className={seg.timing_source === "missing" ? "text-amber-300" : seg.timing_source === "derived_split" ? "text-cyan-300/80" : ""}>{TIMING_LABELS[seg.timing_source]}</span>
          </div>
          {dirty && (
            <div className="flex gap-2">
              <button className="btn-primary flex-1 py-1.5 text-xs" disabled={saving || timeInvalid} onClick={() => void save()}>{saving ? <Spinner size={13} /> : <Save size={13} />} Save</button>
              <button className="btn-ghost py-1.5 text-xs" onClick={revert}><Undo2 size={13} /></button>
            </div>
          )}
        </div>
      </div>

      {err && <div className="mt-2 text-xs text-rose-300">{err}</div>}
      {rep.issues.length > 0 && (
        <ul className="mt-3 space-y-1 border-t border-white/[0.05] pt-3">
          {rep.issues.map((i, k) => (
            <li key={k} className="flex gap-2 text-xs text-white/65"><SeverityIcon severity={i.severity} />{i.message}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EditorBody({ ep }: { ep: Episode }) {
  const { setEpisode, notify, focusSegmentId, settings, go } = useApp();
  const [character, setCharacter] = useState("all");
  const [status, setStatus] = useState("all");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState<null | "resplit" | "ai">(null);
  const [aiError, setAiError] = useState<string | null>(null);
  const [showWarnings, setShowWarnings] = useState(false);

  const filtered = useMemo(() => ep.segments.filter((s) => {
    const r = ep.report.segments[s.id];
    if (character !== "all" && s.character !== character) return false;
    if (status === "missing" && !(s.start_ms === null || s.end_ms === null)) return false;
    if (["good", "warning", "error"].includes(status) && r.status !== status) return false;
    if (q && !s.text.toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  }), [ep, character, status, q]);

  const resplit = async () => {
    if (!window.confirm("Re-split every line from the original screenplay using the current thresholds? Manual edits, manual timings and AI suggestions in this episode will be discarded.")) return;
    setBusy("resplit");
    try { setEpisode(await api.resplit(ep.id)); notify("Episode re-split from the original screenplay."); }
    catch (e) { notify((e as Error).message, "error"); }
    finally { setBusy(null); }
  };
  const aiSegment = async () => {
    setBusy("ai");
    setAiError(null);
    try {
      const res = await api.aiSegment(ep.id);
      setEpisode(res);
      const r = res.ai_result;
      notify(`AI segmentation: ${r?.accepted ?? 0} line(s) re-segmented, ${r?.rejected.length ?? 0} kept deterministic.`, "info");
    } catch (e) { setAiError((e as Error).message); }
    finally { setBusy(null); }
  };

  const missing = ep.segments.filter((s) => s.start_ms === null || s.end_ms === null).length;

  return (
    <>
      <PageHeader eyebrow={ep.project_name} title="Subtitle Editor"
        subtitle={<span className="inline-flex flex-wrap items-center gap-2">{ep.name} · {ep.dialogue.length} dialogue lines → {ep.segments.length} subtitle cards · {ep.characters.length} characters {ep.is_synthetic && <SyntheticBadge />}</span>}
        actions={<>
          <button className="btn-ghost" onClick={() => void resplit()} disabled={!!busy}>{busy === "resplit" ? <Spinner /> : <RotateCcw size={15} />} Re-split</button>
          <button className="btn-cyan" onClick={() => void aiSegment()} disabled={!!busy} title={`Uses ${settings?.model}`}>{busy === "ai" ? <Spinner /> : <Scissors size={15} />} AI segmentation</button>
          <button className="btn-primary" onClick={() => go("optimizer")}><Sparkles size={15} /> Optimise dialogue</button>
        </>} />

      {aiError && (
        <ErrorBanner title="AI segmentation unavailable" message={aiError} onClose={() => setAiError(null)}>
          <div className="mt-1 text-xs text-rose-100/60">Nothing was changed. The deterministic split and all readability checks below remain valid.</div>
        </ErrorBanner>
      )}

      {missing > 0 && (
        <div className="mb-4 flex items-center gap-2 rounded-xl border border-amber-300/20 bg-amber-400/[0.05] px-4 py-2.5 text-sm text-amber-100/85">
          <TriangleAlert size={15} className="text-amber-300" />
          {missing} card{missing === 1 ? " has" : "s have"} no timing in the screenplay. Timestamps are never invented — enter them manually below.
          <button className="ml-auto text-xs text-amber-200 underline-offset-2 hover:underline" onClick={() => setStatus("missing")}>Show them</button>
        </div>
      )}

      {ep.warnings.length > 0 && (
        <div className="mb-4 card">
          <button className="flex w-full items-center justify-between px-4 py-3 text-sm" onClick={() => setShowWarnings(!showWarnings)}>
            <span className="text-white/75">Parser notes ({ep.warnings.length})</span>
            <ChevronDown size={16} className={cls("transition-transform", showWarnings && "rotate-180")} />
          </button>
          {showWarnings && <ul className="space-y-1 border-t border-white/[0.05] px-4 py-3 text-xs text-white/55">{ep.warnings.map((w, i) => <li key={i}>• {w}</li>)}</ul>}
        </div>
      )}

      <div className="mb-4 flex flex-wrap gap-2">
        <div className="relative min-w-[200px] flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/35" />
          <input className="input pl-9" placeholder="Search subtitle text…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <select className="input w-auto" value={character} onChange={(e) => setCharacter(e.target.value)} aria-label="Character filter">
          <option value="all">All characters</option>
          {ep.characters.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select className="input w-auto" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter">
          <option value="all">All statuses</option><option value="error">Fix needed</option><option value="warning">Review</option>
          <option value="good">Readable</option><option value="missing">Missing timing</option>
        </select>
      </div>

      <div className="mb-2 text-xs text-white/40">Showing {filtered.length} of {ep.segments.length} cards</div>
      <div className="space-y-3">
        {filtered.map((s) => <SegmentCard key={s.id} ep={ep} seg={s} rep={ep.report.segments[s.id]} focused={focusSegmentId === s.id} />)}
      </div>
    </>
  );
}

export default function Editor() {
  return <RequireEpisode>{(ep) => <EditorBody ep={ep} />}</RequireEpisode>;
}
