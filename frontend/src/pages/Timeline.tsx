import { TriangleAlert, SquarePen, ZoomIn, ZoomOut } from "lucide-react";
import { useMemo, useState } from "react";
import { RequireEpisode } from "../components/RequireEpisode";
import { CharacterChip, PageHeader, StatusBadge, SyntheticBadge } from "../components/ui";
import { useApp } from "../context";
import type { Episode, Segment } from "../types";
import { charColor, cls, fmtTime } from "../utils";

const CARD_W = 190;
const LANE_H = 118;

function Body({ ep }: { ep: Episode }) {
  const { go } = useApp();
  const [pps, setPps] = useState(70); // pixels per second
  const [sel, setSel] = useState<string | null>(ep.segments[0]?.id ?? null);

  const timed = useMemo(() => ep.segments.filter((s) => s.start_ms !== null).sort((a, b) => a.start_ms! - b.start_ms!), [ep]);
  const untimed = ep.segments.filter((s) => s.start_ms === null);
  const endMs = Math.max(10_000, ...timed.map((s) => Math.max(s.end_ms ?? 0, s.start_ms! + 1000)));
  const width = (endMs / 1000) * pps + CARD_W + 40;

  const lanes = useMemo(() => {
    const laneEnds: number[] = [];
    const out: { seg: Segment; lane: number; x: number; w: number }[] = [];
    for (const s of timed) {
      const x = (s.start_ms! / 1000) * pps;
      const durW = s.end_ms !== null && s.end_ms > s.start_ms! ? ((s.end_ms - s.start_ms!) / 1000) * pps : 0;
      const extent = x + Math.max(durW, CARD_W) + 8;
      let lane = laneEnds.findIndex((e) => e <= x);
      if (lane === -1) { lane = laneEnds.length; laneEnds.push(extent); } else laneEnds[lane] = extent;
      out.push({ seg: s, lane, x, w: durW });
    }
    return { items: out, count: Math.max(1, laneEnds.length) };
  }, [timed, pps]);

  const tickEvery = pps >= 60 ? 1 : pps >= 30 ? 2 : 5;
  const labelEvery = pps >= 100 ? 1 : pps >= 50 ? 5 : 10;
  const ticks = Array.from({ length: Math.floor(endMs / 1000 / tickEvery) + 2 }, (_, i) => i * tickEvery);
  const selected = ep.segments.find((s) => s.id === sel) ?? null;
  const selRep = selected ? ep.report.segments[selected.id] : null;

  return (
    <>
      <PageHeader eyebrow={ep.project_name} title="Timeline Preview"
        subtitle={<span className="inline-flex flex-wrap items-center gap-2">{ep.name} · {timed.length} placed cards · {fmtTime(endMs, true)} runtime {ep.is_synthetic && <SyntheticBadge />}</span>}
        actions={<div className="flex items-center gap-2 rounded-xl bg-white/[0.03] px-3 py-1.5 ring-1 ring-white/[0.06]">
          <ZoomOut size={15} className="text-white/50" />
          <input type="range" min={25} max={220} value={pps} onChange={(e) => setPps(Number(e.target.value))} className="w-36 accent-violet-500" aria-label="Zoom" />
          <ZoomIn size={15} className="text-white/50" />
        </div>} />

      <div className="grid gap-4 xl:grid-cols-[1fr_300px]">
        <div className="card min-w-0 p-4">
          <div className="overflow-x-auto pb-3">
            <div className="relative" style={{ width, height: 34 + lanes.count * LANE_H }}>
              {/* ruler */}
              <div className="absolute inset-x-0 top-0 h-7 border-b border-white/10">
                {ticks.map((t) => (
                  <div key={t} className="absolute top-0 h-full" style={{ left: t * pps }}>
                    <div className={cls("w-px", t % labelEvery === 0 ? "h-3 bg-white/40" : "h-2 bg-white/15")} />
                    {t % labelEvery === 0 && <span className="absolute left-1 top-2.5 font-mono text-[10px] text-white/40">{fmtTime(t * 1000, true).replace(/\.\d$/, "")}</span>}
                  </div>
                ))}
              </div>
              {/* grid lines */}
              {ticks.filter((t) => t % labelEvery === 0).map((t) => <div key={`g${t}`} className="absolute bottom-0 top-7 w-px bg-white/[0.04]" style={{ left: t * pps }} />)}
              {/* cards */}
              {lanes.items.map(({ seg, lane, x, w }) => {
                const r = ep.report.segments[seg.id];
                const c = charColor(seg.character);
                const overlap = r.issues.some((i) => i.code === "overlap");
                return (
                  <button key={seg.id} onClick={() => setSel(seg.id)} onDoubleClick={() => go("editor", seg.id)}
                    className="group absolute text-left" style={{ left: x, top: 36 + lane * LANE_H, width: Math.max(w, CARD_W) }}>
                    <div className="mb-1 h-1.5 rounded-full" style={{ width: Math.max(w, 3), background: overlap ? "#fb7185" : c.hex, opacity: 0.85 }} title={`Actual duration ${w ? (w / pps).toFixed(2) + "s" : "unknown"}`} />
                    <div className={cls("rounded-xl border bg-card-2 p-2.5 transition-colors", sel === seg.id ? "border-cyan-400/60" : overlap ? "border-rose-400/50" : "border-white/[0.07] group-hover:border-white/20")} style={{ width: CARD_W }}>
                      <div className="flex items-center justify-between gap-1">
                        <CharacterChip name={seg.character} small />
                        <span className={cls("h-2 w-2 shrink-0 rounded-full", r.status === "good" ? "bg-emerald-400" : r.status === "warning" ? "bg-amber-400" : "bg-rose-400")} title={r.status} />
                      </div>
                      <div className="mt-1 font-mono text-[10px] text-white/40">{fmtTime(seg.start_ms, true)} → {fmtTime(seg.end_ms, true)}</div>
                      <p className="mt-1 line-clamp-2 text-[11.5px] leading-snug text-white/85">{seg.text || <i className="text-white/30">(empty)</i>}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
          <div className="mt-2 flex flex-wrap gap-4 border-t border-white/[0.05] pt-3 text-[11px] text-white/45">
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-emerald-400" /> Readable</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-amber-400" /> Review</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-rose-400" /> Fix needed</span>
            <span className="flex items-center gap-1.5"><span className="h-1.5 w-4 rounded-full bg-rose-400" /> Overlapping cue</span>
            <span>Bar above each card = real on-screen duration · double-click to edit</span>
          </div>

          {untimed.length > 0 && (
            <div className="mt-4 rounded-xl border border-amber-300/20 bg-amber-400/[0.04] p-3">
              <div className="mb-2 flex items-center gap-2 text-xs font-medium text-amber-200"><TriangleAlert size={14} /> Not placed — timing missing in screenplay ({untimed.length})</div>
              <div className="flex flex-wrap gap-2">
                {untimed.map((s) => (
                  <button key={s.id} onClick={() => go("editor", s.id)} className="max-w-[260px] rounded-lg bg-card-2 px-2.5 py-2 text-left ring-1 ring-white/[0.07] hover:ring-amber-300/40">
                    <CharacterChip name={s.character} small />
                    <p className="mt-1 line-clamp-2 text-[11px] text-white/75">{s.text}</p>
                    <span className="mt-1 block text-[10px] text-amber-300">Enter timing →</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Phone preview */}
        <div className="card p-5">
          <h3 className="mb-3 font-display font-semibold">Mobile preview</h3>
          <div className="mx-auto w-[220px] rounded-[30px] border border-white/10 bg-black p-2 shadow-2xl">
            <div className="relative aspect-[9/16] overflow-hidden rounded-[22px] bg-gradient-to-b from-[#1b1530] via-[#0e0e19] to-[#081a22]">
              <div className="absolute left-1/2 top-2 h-1.5 w-14 -translate-x-1/2 rounded-full bg-white/15" />
              <div className="absolute inset-x-3 bottom-14 text-center">
                {selRep?.metrics.lines.map((l, i) => (
                  <div key={i} className="mx-auto mb-0.5 w-fit rounded bg-black/55 px-1.5 text-[11px] font-semibold leading-snug text-white" style={{ textShadow: "0 1px 2px #000" }}>{l}</div>
                ))}
              </div>
            </div>
          </div>
          {selected && selRep ? (
            <div className="mt-4 space-y-2 text-xs">
              <div className="flex items-center gap-2"><CharacterChip name={selected.character} /><StatusBadge status={selRep.status} score={selRep.score} /></div>
              <div className="font-mono text-white/50">{fmtTime(selected.start_ms)} → {fmtTime(selected.end_ms)}</div>
              <div className="text-white/55">{selRep.metrics.chars} chars · {selRep.metrics.line_count} line(s) · {selRep.metrics.cps ? `${selRep.metrics.cps} cps` : "no speed"}</div>
              {selRep.issues.map((i, k) => <div key={k} className="text-white/55">• {i.message}</div>)}
              <button className="btn-ghost mt-2 w-full py-1.5 text-xs" onClick={() => go("editor", selected.id)}><SquarePen size={13} /> Edit this card</button>
            </div>
          ) : <p className="mt-4 text-xs text-white/45">Select a card to preview it on a phone screen.</p>}
        </div>
      </div>
    </>
  );
}

export default function Timeline() {
  return <RequireEpisode>{(ep) => <Body ep={ep} />}</RequireEpisode>;
}
