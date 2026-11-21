import { TriangleAlert, ArrowRight, Captions, Clapperboard, FileUp, FlaskConical, Gauge, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useLoadDemo } from "../components/RequireEpisode";
import { BarChart, EmptyState, ErrorBanner, HBarList, PageHeader, ScoreRing, Spinner, StatCard, SyntheticBadge } from "../components/ui";
import { useApp } from "../context";
import type { DashboardData } from "../types";
import { ISSUE_LABELS, relTime, scoreColor } from "../utils";

export default function Dashboard() {
  const { go, selectProject, refreshProjects, notify, settings, projects } = useApp();
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const demo = useLoadDemo();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.dashboard());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load, projects.length]);

  const remove = async (id: string, name: string) => {
    if (!window.confirm(`Delete project “${name}” and all its episodes? This cannot be undone.`)) return;
    try {
      await api.deleteProject(id);
      await refreshProjects();
      await load();
      notify("Project deleted.");
    } catch (e) {
      notify((e as Error).message, "error");
    }
  };

  const loadDemo = async () => { await demo.run(); await load(); };

  const header = (
    <PageHeader eyebrow="Production overview" title="Subtitle readiness dashboard"
      subtitle="Every number below is computed live from the screenplays you have processed — nothing is estimated or pre-filled."
      actions={<>
        <button className="btn-ghost" onClick={() => void load()} disabled={loading}>{loading ? <Spinner /> : <RefreshCw size={15} />} Refresh</button>
        <button className="btn-cyan" onClick={() => void loadDemo()} disabled={demo.loading}>{demo.loading ? <Spinner /> : <FlaskConical size={15} />} Load synthetic demo</button>
      </>} />
  );

  if (error) return <>{header}<ErrorBanner title="Could not load dashboard" message={error} /></>;
  if (!data) return <>{header}<div className="flex items-center gap-2 text-white/60"><Spinner /> Loading…</div></>;

  if (data.total_episodes === 0) {
    return (
      <>
        {header}
        <EmptyState icon={<Clapperboard size={24} />} title="No episodes processed yet"
          body="Upload one or more TXT screenplays, or try the synthetic demo series (fictional data, clearly labelled) to see every feature."
          action={<>
            <button className="btn-primary" onClick={() => go("upload")}><FileUp size={15} /> Upload screenplays</button>
            <button className="btn-ghost" onClick={() => void loadDemo()} disabled={demo.loading}>{demo.loading ? <Spinner /> : <FlaskConical size={15} />} Load synthetic demo</button>
          </>} />
      </>
    );
  }

  const labels = data.activity.map((a) => new Date(a.date + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" }));
  const breakdown = Object.entries(data.issue_breakdown).map(([k, v]) => ({ label: ISSUE_LABELS[k] ?? k, value: v }));

  return (
    <>
      {header}
      {data.synthetic_episodes > 0 && (
        <div className="mb-5 flex items-center gap-2 rounded-xl border border-amber-300/20 bg-amber-400/[0.05] px-4 py-2.5 text-xs text-amber-100/80">
          <FlaskConical size={14} className="text-amber-300" />
          {data.synthetic_episodes} of {data.total_episodes} episodes are <b className="text-amber-200">synthetic demo data</b> and are included in these totals. Delete the demo project to see real production data only.
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={<Clapperboard size={16} />} label="Episodes processed" value={data.total_episodes}
          sub={`${data.total_projects} project${data.total_projects === 1 ? "" : "s"} · ${data.synthetic_episodes} synthetic`} />
        <StatCard icon={<Captions size={16} />} accent="cyan" label="Subtitle segments" value={data.total_segments}
          sub={`${data.missing_timing} need manual timing`} />
        <StatCard icon={<TriangleAlert size={16} />} accent="rose" label="Readability issues" value={data.readability_issues}
          sub={`${data.readability_errors} errors · info notes excluded`} />
        <div className="card relative flex items-center gap-4 overflow-hidden p-5">
          <div className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full bg-gradient-to-br from-emerald-400/20 to-transparent blur-2xl" />
          <ScoreRing score={data.average_score} size={76} />
          <div>
            <div className="label">Avg quality score</div>
            <div className={`mt-1 font-display text-3xl font-semibold tabular-nums ${scoreColor(data.average_score)}`}>{data.average_score ?? "—"}</div>
            <div className="text-xs text-white/50">Editorial heuristic, 0–100</div>
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <div className="card p-5 xl:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="font-display font-semibold">Processing activity</h3>
              <p className="text-xs text-white/45">Last 14 days · episodes analysed, AI calls and manual edits</p>
            </div>
            <div className="flex gap-3 text-xs">
              <span className="text-emerald-300">{data.ai_runs.success} AI ok</span>
              <span className="text-rose-300">{data.ai_runs.failed} AI failed</span>
            </div>
          </div>
          <BarChart labels={labels} series={[
            { name: "Episodes", color: "#8B5CF6", values: data.activity.map((a) => a.episodes) },
            { name: "AI calls (ok)", color: "#22D3EE", values: data.activity.map((a) => a.ai_success) },
            { name: "AI calls (failed)", color: "#fb7185", values: data.activity.map((a) => a.ai_failed) },
            { name: "Edits & decisions", color: "#a3a3c2", values: data.activity.map((a) => a.edits) },
          ]} />
        </div>
        <div className="card p-5">
          <h3 className="font-display font-semibold">Issue breakdown</h3>
          <p className="mb-4 text-xs text-white/45">Across all episodes, current thresholds</p>
          <HBarList items={breakdown.slice(0, 8)} empty="No issues found." />
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <div className="card overflow-hidden xl:col-span-2">
          <div className="flex items-center justify-between px-5 pt-5">
            <h3 className="font-display font-semibold">Recent projects</h3>
            <button className="text-xs text-cyan-300 hover:text-cyan-200" onClick={() => go("upload")}>+ New project</button>
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-white/40">
                  <th className="px-5 py-2 font-medium">Project</th><th className="px-3 py-2 font-medium">Episodes</th>
                  <th className="px-3 py-2 font-medium">Segments</th><th className="px-3 py-2 font-medium">Issues</th>
                  <th className="px-3 py-2 font-medium">Score</th><th className="px-5 py-2" />
                </tr>
              </thead>
              <tbody>
                {data.recent_projects.map((p) => (
                  <tr key={p.id} className="border-t border-white/[0.05] hover:bg-white/[0.02]">
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2 font-medium">{p.name}{p.is_synthetic && <SyntheticBadge />}</div>
                      <div className="text-xs text-white/40">{relTime(p.created_at)}</div>
                    </td>
                    <td className="px-3 py-3 tabular-nums">{p.episode_count}</td>
                    <td className="px-3 py-3 tabular-nums">{p.segment_count}</td>
                    <td className="px-3 py-3 tabular-nums">{p.issue_count}</td>
                    <td className={`px-3 py-3 font-semibold tabular-nums ${scoreColor(p.average_score)}`}>{p.average_score ?? "—"}</td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex justify-end gap-1.5">
                        <button className="btn-ghost px-2.5 py-1.5 text-xs" onClick={() => { selectProject(p.id, p.first_episode_id ?? undefined); go("editor"); }}>
                          Open <ArrowRight size={13} />
                        </button>
                        <button className="btn-danger px-2.5 py-1.5" title="Delete project" onClick={() => void remove(p.id, p.name)}><Trash2 size={13} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="card p-5">
          <h3 className="font-display font-semibold">Quality distribution</h3>
          <p className="mb-4 text-xs text-white/45">Segments by score band</p>
          <HBarList items={Object.entries(data.score_distribution).map(([k, v]) => ({ label: k, value: v }))} />
          <div className="mt-5 rounded-xl bg-white/[0.03] p-3 text-xs text-white/55 ring-1 ring-white/[0.06]">
            <div className="mb-1 flex items-center gap-1.5 font-medium text-white/75"><Gauge size={13} /> Active guidelines</div>
            ≤{data.thresholds.max_chars_per_line} chars/line · ≤{data.thresholds.max_lines} lines · ≤{data.thresholds.max_cps} cps ·
            {" "}{data.thresholds.min_duration_s}–{data.thresholds.max_duration_s}s on screen
            <button className="mt-2 block text-cyan-300 hover:text-cyan-200" onClick={() => go("settings")}>Adjust thresholds →</button>
          </div>
          <div className="mt-3 flex items-center gap-2 text-xs text-white/50">
            <Sparkles size={13} className="text-violet-300" /> Model: <span className="font-mono text-white/70">{settings?.model}</span>
          </div>
        </div>
      </div>
    </>
  );
}
