import { FileText, FlaskConical, Play, Trash2, CloudUpload } from "lucide-react";
import { useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../api";
import { ErrorBanner, InfoBanner, PageHeader, Spinner, SyntheticBadge } from "../components/ui";
import { useApp } from "../context";
import { cls } from "../utils";

interface Entry { key: string; filename: string; content: string; synthetic: boolean; size: number; file?: File }

const TS_LINE = /^\s*\[?\s*(?:\d{1,2}:)?\d{1,2}:\d{2}|^\s*\[\s*(?:\?\?|--|TBD)/i;
const SCENE = /^\s*(?:INT|EXT|INT\/EXT|I\/E)[.\s]/i;
const INLINE = /^([A-Z][A-Z0-9 .'-]{0,30}?)(\s*\([^)]*\))?\s*:/;
const CUE = /^[A-Z][A-Z0-9 .'-]{0,30}(\s*\([^)]*\))?\s*$/;

function detectEpisodes(e: Entry): string[] {
  const num = /^\s*EPISODE NUMBER\s*:\s*(.+)$/im.exec(e.content);
  if (num) return [num[1].trim()];
  const found = [...e.content.matchAll(/^\s*EPISODE\b(?!\s+(?:LOGLINE|SUMMARY|TITLE)\b)\s*[:#-]?\s*(.*)$/gim)].map((m) => {
    const rest = m[1].trim();
    const n = /^(\d+)\s*[:.\-—–]?\s*(.*)$/.exec(rest);
    return n ? `Episode ${n[1]}${n[2] ? " — " + n[2] : ""}` : rest || "Episode";
  });
  return found.length ? found : [e.filename.replace(/\.[^.]+$/, "").replace(/_/g, " ")];
}

const BOLD_LABEL = /^\*\*([^*]+?):?\*\*:?/;
const NON_DIALOGUE = /^(CAMERA|ACTION|SOUND FX|SFX|SOUND|MUSIC|VFX|TRANSITION|NOTES?|TEXT ON SCREEN|SUPER|TITLE CARD|INSERT|SHOT|DESCRIPTION)\b/i;

function countDialogue(content: string): number {
  // Structured production-script format: **NAME (emotion):** blocks
  const bold = content.split(/\r?\n/).map((l) => BOLD_LABEL.exec(l.trim())).filter((m): m is RegExpExecArray => !!m);
  if (bold.length) return bold.filter((m) => !NON_DIALOGUE.test(m[1].trim())).length;
  let n = 0;
  for (const raw of content.split(/\r?\n/)) {
    const l = raw.trim();
    if (!l || l.startsWith("#")) continue;
    const rest = l.replace(/^\[[^\]]*\]\s*/, "").replace(/^(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d+)?\s*(?:-->|-|–)\s*(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d+)?\s*/, "");
    if (INLINE.test(rest) && !/^(TITLE|EPISODE|NOTE|SERIES)\b/.test(rest) && !/TO:\s*$/.test(rest)) n++;
    else if (rest === l && CUE.test(l) && !SCENE.test(l) && !/TO:$/.test(l) && !/^(FADE|TITLE|EPISODE)/.test(l)) n++;
  }
  return n;
}

function Preview({ content }: { content: string }) {
  const lines = content.split(/\r?\n/);
  return (
    <div className="max-h-[560px] overflow-auto rounded-xl bg-ink/70 p-4 font-mono text-[12.5px] leading-6 ring-1 ring-white/[0.06]">
      {lines.map((l, i) => {
        const t = l.trim();
        let node: ReactNode = l || " ";
        let c = "text-white/70";
        if (t.startsWith("#") || t.startsWith("//")) c = "italic text-white/30";
        else if (SCENE.test(t)) c = "font-semibold text-white";
        else if (/^(TITLE|EPISODE)\b/i.test(t)) c = "font-semibold text-violet-200";
        else if (BOLD_LABEL.test(t)) c = NON_DIALOGUE.test(BOLD_LABEL.exec(t)![1].trim()) ? "text-white/35" : "font-semibold text-violet-300";
        else if (/^Start\s*:/i.test(t)) c = "text-cyan-300";
        else if (TS_LINE.test(t)) {
          const m = /^(\s*\[[^\]]*\]|\s*(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]?\d*\s*(?:-->|-|–)\s*(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]?\d*)(.*)$/.exec(l);
          if (m) {
            const rest = m[2];
            const im = INLINE.exec(rest.trim());
            node = <><span className={/\?\?|TBD|--\]/.test(m[1]) ? "text-amber-300" : "text-cyan-300"}>{m[1]}</span>
              {im ? <> <span className="font-semibold text-violet-300">{im[0]}</span>{rest.trim().slice(im[0].length)}</> : rest}</>;
          }
        } else if (INLINE.test(t)) {
          const im = INLINE.exec(t)!;
          node = <><span className="font-semibold text-violet-300">{im[0]}</span>{t.slice(im[0].length)}</>;
        } else if (CUE.test(t) && t === t.toUpperCase() && /[A-Z]/.test(t) && !/TO:$/.test(t)) c = "font-semibold text-violet-300";
        else if (/^\(.*\)$/.test(t)) c = "italic text-white/45";
        return (
          <div key={i} className="flex gap-4">
            <span className="w-7 shrink-0 select-none text-right text-white/20">{i + 1}</span>
            <span className={cls("whitespace-pre-wrap break-words", c)}>{node}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function Upload() {
  const { refreshProjects, selectProject, go, notify } = useApp();
  const [entries, setEntries] = useState<Entry[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const addFiles = async (files: FileList | File[]) => {
    setError(null);
    const list = Array.from(files);
    const bad = list.filter((f) => !f.name.toLowerCase().endsWith(".txt"));
    if (bad.length) setError(`Skipped ${bad.map((b) => b.name).join(", ")} — only .txt screenplays are accepted.`);
    const added: Entry[] = [];
    for (const f of list.filter((f) => f.name.toLowerCase().endsWith(".txt"))) {
      const content = await f.text();
      added.push({ key: `${f.name}-${f.size}-${f.lastModified}`, filename: f.name, content, size: f.size, file: f, synthetic: /\bSYNTHETIC\b/i.test(content.slice(0, 2000)) });
    }
    setEntries((prev) => {
      const keys = new Set(prev.map((p) => p.key));
      const next = [...prev, ...added.filter((a) => !keys.has(a.key))];
      if (!selected && next[0]) setSelected(next[0].key);
      return next;
    });
    if (added[0]) setSelected(added[0].key);
    if (!name && added[0]) setName(added[0].filename.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " "));
  };

  const addSamples = async () => {
    setError(null);
    try {
      const samples = await api.samples();
      const added = samples.map((s) => ({ key: `sample-${s.filename}`, filename: s.filename, content: s.content, synthetic: true, size: s.content.length }));
      setEntries((prev) => [...prev.filter((p) => !p.key.startsWith("sample-")), ...added]);
      if (added[0]) setSelected(added[0].key);
      if (!name) setName("SYNTHETIC DEMO — Midnight Contract");
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const start = async () => {
    if (!entries.length) return;
    setBusy(true);
    setError(null);
    try {
      const allSamples = entries.every((e) => e.key.startsWith("sample-"));
      const project = allSamples
        ? await api.createSample()
        : await api.createProject(name || "Untitled project", entries.map((e) => e.file ?? new File([e.content], e.filename, { type: "text/plain" })));
      await refreshProjects();
      selectProject(project.id, project.episodes[0]?.id);
      const segs = project.episodes.reduce((a, e) => a + e.segment_count, 0);
      notify(`Analysed ${project.episodes.length} episode(s) into ${segs} subtitle segments.`);
      setEntries([]);
      go("editor");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const current = entries.find((e) => e.key === selected) ?? null;
  const stats = useMemo(() => entries.map((e) => ({ key: e.key, episodes: detectEpisodes(e), lines: countDialogue(e.content) })), [entries]);

  return (
    <>
      <PageHeader eyebrow="Ingest" title="Upload Studio"
        subtitle="Drop one or more plain-text screenplays. Each file — or each EPISODE heading inside a file — becomes an episode. Timestamps are kept exactly as written."
        actions={<>
          <button className="btn-ghost" onClick={() => void addSamples()}><FlaskConical size={15} /> Preview synthetic sample</button>
          <button className="btn-primary" disabled={!entries.length || busy} onClick={() => void start()}>
            {busy ? <Spinner /> : <Play size={15} />} Start analysis
          </button>
        </>} />

      {error && <ErrorBanner title="Upload problem" message={error} onClose={() => setError(null)} />}

      <div className="grid gap-5 xl:grid-cols-[380px_1fr]">
        <div className="space-y-4">
          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); void addFiles(e.dataTransfer.files); }}
            onClick={() => inputRef.current?.click()}
            className={cls("card flex cursor-pointer flex-col items-center justify-center border-2 border-dashed px-6 py-10 text-center transition-colors",
              drag ? "border-cyan-400/60 bg-cyan-400/[0.05]" : "border-white/10 hover:border-violet-400/40")}>
            <div className="mb-3 grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-violet-500/30 to-cyan-400/20 ring-1 ring-white/10"><CloudUpload size={22} /></div>
            <div className="font-medium">Drop .txt screenplays here</div>
            <div className="mt-1 text-xs text-white/45">or click to browse · multiple files supported · max 2 MB each</div>
            <input ref={inputRef} type="file" accept=".txt,text/plain" multiple className="hidden"
              onChange={(e) => { if (e.target.files) void addFiles(e.target.files); e.target.value = ""; }} />
          </div>

          <label className="block">
            <span className="label">Project name</span>
            <input className="input mt-1.5" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Midnight Contract S1" />
          </label>

          <div className="card divide-y divide-white/[0.05]">
            <div className="flex items-center justify-between px-4 py-3">
              <span className="label">Files ({entries.length})</span>
              {entries.length > 0 && <button className="text-xs text-white/50 hover:text-white" onClick={() => { setEntries([]); setSelected(null); }}>Clear all</button>}
            </div>
            {entries.length === 0 && <div className="px-4 py-6 text-center text-sm text-white/40">No files yet.</div>}
            {entries.map((e) => {
              const st = stats.find((s) => s.key === e.key)!;
              return (
                <button key={e.key} onClick={() => setSelected(e.key)}
                  className={cls("flex w-full items-start gap-3 px-4 py-3 text-left transition-colors", selected === e.key ? "bg-violet-500/[0.08]" : "hover:bg-white/[0.02]")}>
                  <FileText size={16} className="mt-0.5 shrink-0 text-violet-300" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2"><span className="truncate text-sm font-medium">{e.filename}</span>{e.synthetic && <SyntheticBadge />}</div>
                    <div className="mt-1 space-y-0.5">
                      {st.episodes.map((ep) => <div key={ep} className="truncate text-xs text-cyan-200/80">▸ {ep}</div>)}
                    </div>
                    <div className="mt-1 text-[11px] text-white/40">~{st.lines} dialogue lines detected · {(e.size / 1024).toFixed(1)} KB</div>
                  </div>
                  <span role="button" tabIndex={0} title="Remove" className="text-white/30 hover:text-rose-300"
                    onClick={(ev) => { ev.stopPropagation(); setEntries((p) => p.filter((x) => x.key !== e.key)); if (selected === e.key) setSelected(null); }}>
                    <Trash2 size={14} />
                  </span>
                </button>
              );
            })}
          </div>

          <div className="card p-4 text-xs leading-5 text-white/55">
            <div className="mb-2 font-medium text-white/80">Supported formats</div>
            <code className="block whitespace-pre-wrap rounded-lg bg-ink/70 p-2.5 font-mono text-[11px] text-cyan-100/80">{`[00:00:01,000 --> 00:00:03,500] MAYA: Who are you?
[00:00:04.0 - 00:00:09.5] ADRIAN (quietly): Someone.

[00:00:10,000 --> 00:00:14,000]
ADRIAN
(turning)
Block-style dialogue works too.

[??:??] LILY: Missing timing is flagged.`}</code>
          </div>
        </div>

        <div className="card min-w-0 p-5">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="font-display font-semibold">Original screenplay preview</h3>
              <p className="text-xs text-white/45">{current ? current.filename : "Select a file to preview"} · <span className="text-cyan-300">timestamps</span> · <span className="text-violet-300">characters</span> · <span className="text-amber-300">missing timing</span></p>
            </div>
            {current?.synthetic && <SyntheticBadge />}
          </div>
          {current?.synthetic && (
            <InfoBanner tone="amber" icon={<FlaskConical size={16} className="mt-0.5 shrink-0 text-amber-300" />}>
              This is a <b>synthetic sample</b> written to demonstrate FrameFlow AI. Its characters, plot and timings are fictional and it deliberately contains overlaps, missing timestamps and over-long lines.
            </InfoBanner>
          )}
          {current ? <Preview content={current.content} /> : (
            <div className="grid h-80 place-items-center rounded-xl bg-ink/50 text-sm text-white/35 ring-1 ring-white/[0.05]">Nothing to preview yet.</div>
          )}
        </div>
      </div>
    </>
  );
}
