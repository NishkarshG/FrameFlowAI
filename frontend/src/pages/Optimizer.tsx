import { ArrowRight, Check, ChevronDown, Cpu, FileJson, KeyRound, ListChecks, RefreshCw, ShieldAlert, Sparkles, Undo2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { RequireEpisode } from "../components/RequireEpisode";
import { CharacterChip, ErrorBanner, InfoBanner, PageHeader, Spinner, StatusBadge } from "../components/ui";
import { useApp } from "../context";
import type { AIRun, Episode, ModelInfo, Segment } from "../types";
import { cls, ISSUE_LABELS, relTime } from "../utils";

const OPTIMIZABLE = new Set(["too_many_chars", "long_line", "too_many_lines", "reading_speed", "long_sentence", "difficult_words"]);

function cpsFor(seg: Segment, text: string) {
  if (seg.start_ms === null || seg.end_ms === null || seg.end_ms <= seg.start_ms) return null;
  return text.length / ((seg.end_ms - seg.start_ms) / 1000);
}

function SuggestionRow({ ep, seg }: { ep: Episode; seg: Segment }) {
  const { setEpisode, notify } = useApp();
  const sug = seg.suggestion!;
  const [draft, setDraft] = useState(sug.text);
  const [busy, setBusy] = useState(false);
  useEffect(() => setDraft(sug.text), [sug.text]);
  const original = sug.status === "accepted" ? seg.original_text : seg.text;
  const before = cpsFor(seg, original), after = cpsFor(seg, draft);
  const maxCps = ep.thresholds.max_cps;

  const act = async (action: "accept" | "reject") => {
    setBusy(true);
    try {
      setEpisode(await api.suggestion(ep.id, seg.id, action, action === "accept" ? draft : undefined));
      notify(action === "accept" ? `Suggestion applied to #${seg.index + 1}.` : `Suggestion rejected for #${seg.index + 1}.`, action === "accept" ? "success" : "info");
    } catch (e) { notify((e as Error).message, "error"); }
    finally { setBusy(false); }
  };
  const revert = async () => {
    setBusy(true);
    try { setEpisode(await api.updateSegment(ep.id, seg.id, { text: seg.original_text })); notify("Original text restored."); }
    catch (e) { notify((e as Error).message, "error"); }
    finally { setBusy(false); }
  };

  return (
    <div className={cls("card p-4", sug.status === "accepted" && "ring-1 ring-emerald-400/25", sug.status === "rejected" && "opacity-60")}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-white/35">#{seg.index + 1}</span>
        <CharacterChip name={seg.character} />
        {seg.parenthetical && <span className="text-xs italic text-white/45">({seg.parenthetical})</span>}
        <span className={cls("ml-auto rounded-full px-2 py-0.5 text-[11px] ring-1",
          sug.status === "pending" ? "bg-violet-500/10 text-violet-200 ring-violet-400/30" : sug.status === "accepted" ? "bg-emerald-400/10 text-emerald-200 ring-emerald-400/30" : "bg-white/5 text-white/50 ring-white/10")}>
          {sug.status}
        </span>
      </div>
      <div className="grid gap-3 md:grid-cols-[1fr_auto_1fr] md:items-stretch">
        <div className="rounded-xl bg-ink/60 p-3 ring-1 ring-white/[0.06]">
          <div className="label mb-1.5">Original</div>
          <p className="text-[15px] leading-relaxed text-white/85">{original}</p>
          <div className="mt-2 text-[11px] text-white/40">{original.length} chars · {before ? `${before.toFixed(1)} cps` : "no timing"}</div>
        </div>
        <div className="hidden items-center md:flex"><ArrowRight className="text-white/25" size={18} /></div>
        <div className="rounded-xl bg-gradient-to-br from-violet-500/[0.10] to-cyan-400/[0.05] p-3 ring-1 ring-violet-400/25">
          <div className="label mb-1.5 flex items-center gap-1.5"><Sparkles size={11} className="text-violet-300" /> Suggested</div>
          {sug.status === "pending" ? (
            <textarea className="w-full resize-y bg-transparent text-[15px] leading-relaxed text-white outline-none" rows={2} value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Suggested text" />
          ) : <p className="text-[15px] leading-relaxed text-white">{sug.text}</p>}
          <div className="mt-2 text-[11px] text-white/45">
            {draft.length} chars <span className="text-emerald-300">({draft.length - original.length >= 0 ? "+" : ""}{draft.length - original.length})</span> ·{" "}
            <span className={after && after > maxCps ? "text-amber-300" : ""}>{after ? `${after.toFixed(1)} cps` : "no timing"}</span>
          </div>
        </div>
      </div>
      {sug.rationale && <p className="mt-3 text-xs text-white/55"><b className="text-white/70">Why:</b> {sug.rationale}</p>}
      {sug.preserved_details.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">{sug.preserved_details.map((d) => <span key={d} className="rounded-md bg-white/[0.05] px-1.5 py-0.5 text-[10px] text-white/55">{d}</span>)}</div>
      )}
      {sug.guard_warnings.length > 0 && (
        <div className="mt-3 space-y-1 rounded-lg bg-amber-400/[0.06] p-2.5 ring-1 ring-amber-300/20">
          {sug.guard_warnings.map((w) => <div key={w} className="flex gap-1.5 text-xs text-amber-100/85"><ShieldAlert size={13} className="mt-0.5 shrink-0 text-amber-300" />{w}</div>)}
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {sug.status === "pending" && <>
          <button className="btn-primary py-1.5 text-xs" disabled={busy || !draft.trim()} onClick={() => void act("accept")}>{busy ? <Spinner size={13} /> : <Check size={14} />} Accept{draft !== sug.text ? " edited" : ""}</button>
          <button className="btn-ghost py-1.5 text-xs" disabled={busy} onClick={() => void act("reject")}><X size={14} /> Reject</button>
        </>}
        {sug.status === "accepted" && seg.text !== seg.original_text && (
          <button className="btn-ghost py-1.5 text-xs" disabled={busy} onClick={() => void revert()}><Undo2 size={14} /> Restore original</button>
        )}
        <span className="ml-auto font-mono text-[10px] text-white/30">{sug.model}</span>
      </div>
    </div>
  );
}

function RawRuns({ ep }: { ep: Episode }) {
  const [runs, setRuns] = useState<AIRun[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const load = useCallback(async () => { try { setRuns(await api.aiRuns(ep.id)); } catch { setRuns([]); } }, [ep.id]);
  useEffect(() => { void load(); }, [load, ep.updated_at]);
  return (
    <div className="card p-5">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="flex items-center gap-2 font-display font-semibold"><FileJson size={16} className="text-cyan-300" /> Raw AI outputs</h3>
          <p className="text-xs text-white/45">Unedited model replies and errors for this episode, newest first. Also saved to <code>raw_ai_outputs/</code>.</p>
        </div>
        <button className="btn-ghost px-2.5 py-1.5" onClick={() => void load()} aria-label="Reload"><RefreshCw size={14} /></button>
      </div>
      {runs === null ? <Spinner /> : runs.length === 0 ? <div className="py-4 text-center text-sm text-white/40">No AI calls yet for this episode.</div> : (
        <div className="space-y-2">
          {runs.map((r) => (
            <div key={r.id} className="rounded-xl bg-ink/60 ring-1 ring-white/[0.06]">
              <button className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs" onClick={() => setOpen(open === r.id ? null : r.id)}>
                <span className={cls("h-2 w-2 rounded-full", r.status === "success" ? "bg-emerald-400" : "bg-rose-400")} />
                <span className="font-medium capitalize">{r.kind}</span>
                <span className="font-mono text-white/40">{r.model}</span>
                <span className="ml-auto text-white/40">{relTime(r.created_at)}</span>
                <ChevronDown size={14} className={cls("text-white/40 transition-transform", open === r.id && "rotate-180")} />
              </button>
              {open === r.id && (
                <div className="border-t border-white/[0.05] px-3 py-2">
                  {r.error && <div className="mb-2 text-xs text-rose-300">Error: {r.error}</div>}
                  <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-black/40 p-2.5 font-mono text-[11px] text-white/70">{r.raw_output ?? "(no output returned)"}</pre>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Body({ ep }: { ep: Episode }) {
  const { settings, setSettings, setEpisode, notify, go } = useApp();
  const [model, setModel] = useState(settings?.model ?? "openrouter/free");
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [modelsErr, setModelsErr] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"pending" | "all">("pending");
  useEffect(() => { if (settings) setModel(settings.model); }, [settings]);

  const candidates = useMemo(() => ep.segments.filter((s) => s.text.trim() && ep.report.segments[s.id].issues.some((i) => OPTIMIZABLE.has(i.code))), [ep]);
  const withSug = ep.segments.filter((s) => s.suggestion && (tab === "all" || s.suggestion.status === "pending"));
  const pendingCount = ep.segments.filter((s) => s.suggestion?.status === "pending").length;

  const loadModels = async () => {
    setModelsErr(null);
    try { setModels(await api.models()); } catch (e) { setModelsErr((e as Error).message); }
  };
  const saveModel = async () => {
    try { setSettings(await api.saveSettings({ model })); notify(`Default model set to ${model}.`); }
    catch (e) { notify((e as Error).message, "error"); }
  };
  const run = async (ids?: string[]) => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.optimize(ep.id, ids, model);
      setEpisode(res);
      setSelected(new Set());
      setTab("pending");
      const r = res.ai_result;
      notify(`${r?.suggested ?? 0} suggestion(s) received from ${r?.model}. ${r?.rejected.length ? `${r.rejected.length} not usable.` : ""}`, "info");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const toggle = (id: string) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  return (
    <>
      <PageHeader eyebrow={ep.project_name} title="AI Dialogue Optimizer"
        subtitle="Shorter alternatives that keep meaning, emotional tone and every plot detail. Nothing changes until you accept it."
        actions={<>
          <button className="btn-ghost" disabled={busy || selected.size === 0} onClick={() => void run([...selected])}><ListChecks size={15} /> Optimise selected ({selected.size})</button>
          <button className="btn-primary" disabled={busy || candidates.length === 0} onClick={() => void run()}>{busy ? <Spinner /> : <Sparkles size={15} />} Optimise all flagged ({Math.min(candidates.length, 25)})</button>
        </>} />

      {settings && !settings.ai.api_key_configured && (
        <InfoBanner tone="amber" icon={<KeyRound size={18} className="mt-0.5 shrink-0 text-amber-300" />}>
          <b className="text-amber-100">No OpenRouter API key configured.</b> Add <code className="rounded bg-black/30 px-1">OPENROUTER_API_KEY</code> to <code className="rounded bg-black/30 px-1">backend/.env</code> and restart the backend.
          Requests will fail with a clear error until then — readability checks, editing, timeline and exports keep working.
        </InfoBanner>
      )}
      {error && (
        <ErrorBanner title="AI optimisation did not complete" message={error} onClose={() => setError(null)}>
          <div className="mt-1 text-xs text-rose-100/60">No suggestions were created and your subtitles are unchanged. Deterministic checks are still available in Readability Intelligence.
            <button className="ml-1 underline" onClick={() => go("readability")}>Open checks →</button></div>
        </ErrorBanner>
      )}

      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <div className="min-w-0 space-y-4">
          <div className="flex items-center gap-1 rounded-xl bg-white/[0.03] p-1 ring-1 ring-white/[0.06] w-fit">
            {(["pending", "all"] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)} className={cls("rounded-lg px-3 py-1.5 text-xs", tab === t ? "bg-violet-500/20 text-white" : "text-white/55 hover:text-white")}>
                {t === "pending" ? `Awaiting review (${pendingCount})` : "All suggestions"}
              </button>
            ))}
          </div>
          {withSug.length === 0 ? (
            <div className="card px-6 py-12 text-center text-sm text-white/45">
              {tab === "pending" ? "No suggestions awaiting review. Select flagged cards on the right or optimise all flagged cards." : "No suggestions generated yet for this episode."}
            </div>
          ) : withSug.map((s) => <SuggestionRow key={s.id} ep={ep} seg={s} />)}
          <RawRuns ep={ep} />
        </div>

        <div className="space-y-4">
          <div className="card p-5">
            <h3 className="mb-3 flex items-center gap-2 font-display font-semibold"><Cpu size={16} className="text-violet-300" /> Model</h3>
            <input className="input font-mono text-xs" list="model-list" value={model} onChange={(e) => setModel(e.target.value.trim())} aria-label="Model id" />
            <datalist id="model-list">{models?.map((m) => <option key={m.id} value={m.id}>{m.free ? "free · " : ""}{m.name}</option>)}</datalist>
            <div className="mt-2 flex flex-wrap gap-2">
              <button className="btn-ghost py-1.5 text-xs" onClick={() => void loadModels()}>Load model list</button>
              <button className="btn-ghost py-1.5 text-xs" disabled={!model || model === settings?.model} onClick={() => void saveModel()}>Make default</button>
            </div>
            {models && <div className="mt-2 text-[11px] text-white/40">{models.filter((m) => m.free).length} free models available — start typing to search.</div>}
            {modelsErr && <div className="mt-2 text-[11px] text-rose-300">{modelsErr}</div>}
            <p className="mt-3 text-[11px] leading-5 text-white/40">Default <code>openrouter/free</code> routes to an available free model. Output quality varies by model; every reply is validated against a strict JSON schema and plot-detail guard before you see it.</p>
          </div>

          <div className="card p-5">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="font-display font-semibold">Flagged cards ({candidates.length})</h3>
              {candidates.length > 0 && <button className="text-xs text-cyan-300" onClick={() => setSelected(selected.size === candidates.length ? new Set() : new Set(candidates.map((c) => c.id)))}>{selected.size === candidates.length ? "Clear" : "Select all"}</button>}
            </div>
            {candidates.length === 0 && <div className="py-4 text-center text-sm text-white/40">No cards exceed length or reading-speed guidelines.</div>}
            <div className="max-h-[560px] space-y-2 overflow-y-auto pr-1">
              {candidates.map((s) => {
                const r = ep.report.segments[s.id];
                return (
                  <label key={s.id} className={cls("flex cursor-pointer gap-3 rounded-xl p-3 ring-1 transition-colors", selected.has(s.id) ? "bg-violet-500/[0.08] ring-violet-400/30" : "bg-ink/50 ring-white/[0.05] hover:ring-white/15")}>
                    <input type="checkbox" className="mt-1 accent-violet-500" checked={selected.has(s.id)} onChange={() => toggle(s.id)} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2"><span className="font-mono text-[11px] text-white/35">#{s.index + 1}</span><CharacterChip name={s.character} small /><StatusBadge status={r.status} /></div>
                      <p className="mt-1 line-clamp-2 text-xs text-white/75">{s.text}</p>
                      <div className="mt-1 flex flex-wrap gap-1">{r.issues.filter((i) => OPTIMIZABLE.has(i.code)).map((i) => <span key={i.code} className="rounded bg-white/[0.05] px-1.5 py-0.5 text-[10px] text-white/50">{ISSUE_LABELS[i.code]}</span>)}</div>
                      {s.suggestion && <div className="mt-1 text-[10px] text-violet-300">has {s.suggestion.status} suggestion</div>}
                    </div>
                  </label>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

export default function Optimizer() {
  return <RequireEpisode>{(ep) => <Body ep={ep} />}</RequireEpisode>;
}
