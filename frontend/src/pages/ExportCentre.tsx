import { TriangleAlert, Archive, Captions, FileJson, FileSpreadsheet, FlaskConical } from "lucide-react";
import { useEffect, useState } from "react";
import { api, download } from "../api";
import { RequireEpisode } from "../components/RequireEpisode";
import { InfoBanner, PageHeader, Spinner, SyntheticBadge } from "../components/ui";
import { useApp } from "../context";
import type { Episode } from "../types";
import { scoreColor } from "../utils";

function Body({ ep }: { ep: Episode }) {
  const { project, notify } = useApp();
  const [busy, setBusy] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ text: string; skipped: number } | null>(null);

  useEffect(() => {
    let alive = true;
    api.exportText(`/api/episodes/${ep.id}/export/srt`).then((p) => alive && setPreview(p)).catch(() => alive && setPreview(null));
    return () => { alive = false; };
  }, [ep.id, ep.updated_at]);

  const dl = async (key: string, path: string) => {
    setBusy(key);
    try {
      const r = await download(path);
      notify(`Downloaded ${r.filename}${r.skipped ? ` — ${r.skipped} card(s) without valid timing were left out` : ""}.`, r.skipped ? "info" : "success");
    } catch (e) { notify((e as Error).message, "error"); }
    finally { setBusy(null); }
  };

  const formats = [
    { key: "srt", icon: Captions, title: "SRT subtitles", body: "Standard SubRip file, lines wrapped to your guideline, ordered by start time.", path: "srt" },
    { key: "csv", icon: FileSpreadsheet, title: "CSV subtitle report", body: "One row per card: timing, metrics, score, issues, original vs current text, AI suggestion status.", path: "csv" },
    { key: "json", icon: FileJson, title: "JSON analysis report", body: "Full analysis with thresholds, disclaimer, per-card readability and raw unedited AI outputs.", path: "json" },
  ];

  return (
    <>
      <PageHeader eyebrow={ep.project_name} title="Export Centre" subtitle="Download deliverables for the selected episode, or everything in the project as one ZIP." />

      {ep.is_synthetic && (
        <InfoBanner tone="amber" icon={<FlaskConical size={18} className="mt-0.5 shrink-0 text-amber-300" />}>
          This episode is <b>synthetic demo data</b>. Exported filenames are prefixed with <code className="rounded bg-black/30 px-1">SYNTHETIC_</code> and reports state the data origin, so they can't be mistaken for production files.
        </InfoBanner>
      )}
      {preview && preview.skipped > 0 && (
        <InfoBanner tone="amber" icon={<TriangleAlert size={18} className="mt-0.5 shrink-0 text-amber-300" />}>
          {preview.skipped} card(s) have missing or invalid timing and will be <b>left out of the SRT</b> (timestamps are never guessed). Fix them in the Subtitle Editor to include them. The CSV and JSON reports include every card.
        </InfoBanner>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        {formats.map((f) => (
          <div key={f.key} className="card flex flex-col p-5">
            <div className="mb-3 grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-violet-500/25 to-cyan-400/15 ring-1 ring-white/10"><f.icon size={18} /></div>
            <h3 className="font-display font-semibold">{f.title}</h3>
            <p className="mt-1 flex-1 text-sm text-white/55">{f.body}</p>
            <button className="btn-primary mt-4" disabled={!!busy} onClick={() => void dl(f.key, `/api/episodes/${ep.id}/export/${f.path}`)}>
              {busy === f.key ? <Spinner /> : <f.icon size={15} />} Download .{f.key}
            </button>
          </div>
        ))}
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_420px]">
        <div className="card min-w-0 p-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-display font-semibold">SRT preview · {ep.name}</h3>
            {ep.is_synthetic && <SyntheticBadge />}
          </div>
          <pre className="max-h-[440px] overflow-auto whitespace-pre-wrap rounded-xl bg-ink/70 p-4 font-mono text-[12px] leading-5 text-white/75 ring-1 ring-white/[0.06]">
            {preview ? preview.text || "(no timed cards yet)" : "Loading…"}
          </pre>
        </div>
        <div className="card p-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-display font-semibold">Project episodes</h3>
            {project && (
              <button className="btn-cyan py-1.5 text-xs" disabled={!!busy} onClick={() => void dl("zip", `/api/projects/${project.id}/export/zip`)}>
                {busy === "zip" ? <Spinner size={13} /> : <Archive size={14} />} All as ZIP
              </button>
            )}
          </div>
          <div className="space-y-2">
            {project?.episodes.map((e) => (
              <div key={e.id} className="rounded-xl bg-ink/50 p-3 ring-1 ring-white/[0.05]">
                <div className="flex items-center gap-2 text-sm font-medium">{e.name}{e.is_synthetic && <SyntheticBadge />}</div>
                <div className="mt-1 text-[11px] text-white/45">
                  {e.segment_count} cards · {e.issue_count} issues · <span className={scoreColor(e.average_score)}>score {e.average_score ?? "—"}</span>
                  {e.missing_timing > 0 && <span className="text-amber-300"> · {e.missing_timing} untimed</span>}
                </div>
                <div className="mt-2 flex gap-1.5">
                  {(["srt", "csv", "json"] as const).map((k) => (
                    <button key={k} className="btn-ghost px-2.5 py-1 text-[11px]" disabled={!!busy} onClick={() => void dl(`${e.id}-${k}`, `/api/episodes/${e.id}/export/${k}`)}>
                      {busy === `${e.id}-${k}` ? <Spinner size={12} /> : null}.{k}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

export default function ExportCentre() {
  return <RequireEpisode>{(ep) => <Body ep={ep} />}</RequireEpisode>;
}
