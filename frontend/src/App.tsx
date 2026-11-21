import {
  ChartColumn, Clapperboard, Download, FileUp, SquareChartGantt, Gauge, Menu, Settings as SettingsIcon, Sparkles, SquarePen, X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { Spinner, SyntheticBadge, Toast } from "./components/ui";
import { AppContext, type AppState } from "./context";
import Dashboard from "./pages/Dashboard";
import Editor from "./pages/Editor";
import ExportCentre from "./pages/ExportCentre";
import Optimizer from "./pages/Optimizer";
import Readability from "./pages/Readability";
import SettingsPage from "./pages/Settings";
import Timeline from "./pages/Timeline";
import Upload from "./pages/Upload";
import type { Episode, Page, Project, Settings } from "./types";
import { cls } from "./utils";

const NAV: { id: Page; label: string; icon: typeof Gauge; group: string }[] = [
  { id: "dashboard", label: "Dashboard", icon: Gauge, group: "Overview" },
  { id: "upload", label: "Upload Studio", icon: FileUp, group: "Overview" },
  { id: "editor", label: "Subtitle Editor", icon: SquarePen, group: "Episode" },
  { id: "readability", label: "Readability Intelligence", icon: ChartColumn, group: "Episode" },
  { id: "optimizer", label: "AI Dialogue Optimizer", icon: Sparkles, group: "Episode" },
  { id: "timeline", label: "Timeline Preview", icon: SquareChartGantt, group: "Episode" },
  { id: "export", label: "Export Centre", icon: Download, group: "Episode" },
  { id: "settings", label: "Settings", icon: SettingsIcon, group: "System" },
];

export default function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [episode, setEpisodeState] = useState<Episode | null>(null);
  const [episodeLoading, setEpisodeLoading] = useState(false);
  const [focusSegmentId, setFocus] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; tone: "success" | "error" | "info" } | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const [backendDown, setBackendDown] = useState<string | null>(null);

  const notify = useCallback((message: string, tone: "success" | "error" | "info" = "success") => {
    setToast({ message, tone });
    window.setTimeout(() => setToast((t) => (t?.message === message ? null : t)), 5000);
  }, []);

  const refreshProjects = useCallback(async () => {
    const list = await api.projects();
    setProjects(list);
    return list;
  }, []);

  const selectEpisode = useCallback(async (id: string) => {
    setEpisodeLoading(true);
    try {
      const ep = await api.episode(id);
      setEpisodeState(ep);
      setProjectId(ep.project_id);
      localStorage.setItem("ff.episode", id);
    } catch (e) {
      notify((e as Error).message, "error");
    } finally {
      setEpisodeLoading(false);
    }
  }, [notify]);

  const selectProject = useCallback((id: string, episodeId?: string) => {
    setProjectId(id);
    const p = projects.find((x) => x.id === id);
    const target = episodeId ?? p?.episodes[0]?.id;
    if (target) void selectEpisode(target);
    else setEpisodeState(null);
  }, [projects, selectEpisode]);

  const setEpisode = useCallback((e: Episode) => {
    setEpisodeState(e);
    // keep summaries in the project list fresh
    void refreshProjects();
  }, [refreshProjects]);

  useEffect(() => {
    (async () => {
      try {
        const [s, list] = await Promise.all([api.settings(), api.projects()]);
        setSettings(s);
        setProjects(list);
        const saved = localStorage.getItem("ff.episode");
        const all = list.flatMap((p) => p.episodes.map((e) => e.id));
        if (saved && all.includes(saved)) void selectEpisode(saved);
        else if (all.length) void selectEpisode(all[0]);
      } catch (e) {
        setBackendDown((e as Error).message);
      }
    })();
  }, [selectEpisode]);

  const project = useMemo(() => projects.find((p) => p.id === projectId) ?? null, [projects, projectId]);

  const go = useCallback((p: Page, focus?: string) => {
    setPage(p);
    setFocus(focus ?? null);
    setNavOpen(false);
    window.scrollTo({ top: 0 });
  }, []);

  const ctx: AppState = {
    settings, setSettings, projects, refreshProjects, project, episode, episodeLoading, setEpisode,
    selectProject, selectEpisode: (id) => void selectEpisode(id), go, focusSegmentId, notify,
  };

  const groups = Array.from(new Set(NAV.map((n) => n.group)));

  return (
    <AppContext.Provider value={ctx}>
      <div className="flex min-h-full">
        {/* Sidebar */}
        <aside className={cls(
          "fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-white/[0.06] bg-panel transition-transform lg:translate-x-0",
          navOpen ? "translate-x-0" : "-translate-x-full",
        )}>
          <div className="flex items-center gap-3 px-5 pb-6 pt-6">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-violet-500 to-cyan-400 shadow-[0_8px_24px_-8px_rgba(139,92,246,0.9)]">
              <Clapperboard size={18} />
            </div>
            <div>
              <div className="font-display text-[15px] font-semibold leading-tight">FrameFlow <span className="text-cyan-300">AI</span></div>
              <div className="text-[11px] text-white/45">Microdrama subtitle studio</div>
            </div>
            <button className="ml-auto text-white/50 lg:hidden" onClick={() => setNavOpen(false)} aria-label="Close menu"><X size={18} /></button>
          </div>
          <nav className="flex-1 space-y-6 overflow-y-auto px-3">
            {groups.map((g) => (
              <div key={g}>
                <div className="label mb-2 px-3">{g}</div>
                <div className="space-y-0.5">
                  {NAV.filter((n) => n.group === g).map((n) => {
                    const active = page === n.id;
                    return (
                      <button key={n.id} onClick={() => go(n.id)}
                        className={cls("group flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm transition-colors",
                          active ? "bg-gradient-to-r from-violet-500/20 to-violet-500/[0.03] text-white ring-1 ring-violet-400/25" : "text-white/60 hover:bg-white/[0.04] hover:text-white")}>
                        <n.icon size={17} className={active ? "text-violet-300" : "text-white/40 group-hover:text-white/70"} />
                        {n.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </nav>
          <div className="m-3 rounded-xl border border-white/[0.06] bg-card/60 p-3 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-white/50">AI engine</span>
              <span className={cls("inline-flex items-center gap-1.5", settings?.ai.api_key_configured ? "text-emerald-300" : "text-amber-300")}>
                <span className={cls("h-1.5 w-1.5 rounded-full", settings?.ai.api_key_configured ? "bg-emerald-400" : "bg-amber-400")} />
                {settings ? (settings.ai.api_key_configured ? "Key set" : "No API key") : "…"}
              </span>
            </div>
            <div className="mt-1 truncate font-mono text-[11px] text-white/45" title={settings?.model}>{settings?.model ?? "—"}</div>
          </div>
        </aside>
        {navOpen && <div className="fixed inset-0 z-30 bg-black/60 lg:hidden" onClick={() => setNavOpen(false)} />}

        {/* Main */}
        <div className="flex min-w-0 flex-1 flex-col lg:pl-64">
          <header className="sticky top-0 z-20 flex flex-wrap items-center gap-3 border-b border-white/[0.06] bg-ink/80 px-4 py-3 backdrop-blur md:px-8">
            <button className="btn-ghost px-2.5 lg:hidden" onClick={() => setNavOpen(true)} aria-label="Open menu"><Menu size={18} /></button>
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
              <select className="input w-auto max-w-[260px] py-1.5" value={projectId ?? ""} onChange={(e) => e.target.value && selectProject(e.target.value)} aria-label="Project">
                <option value="" disabled>{projects.length ? "Select project" : "No projects yet"}</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <select className="input w-auto max-w-[260px] py-1.5" value={episode?.id ?? ""} disabled={!project}
                onChange={(e) => e.target.value && void selectEpisode(e.target.value)} aria-label="Episode">
                <option value="" disabled>Select episode</option>
                {project?.episodes.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
              </select>
              {episodeLoading && <Spinner />}
              {episode?.is_synthetic && <SyntheticBadge />}
            </div>
            <button className="btn-primary py-1.5" onClick={() => go("upload")}><FileUp size={15} /> New upload</button>
          </header>

          <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 md:px-8 md:py-8">
            {backendDown && (
              <div className="mb-6 rounded-2xl border border-rose-500/30 bg-rose-500/[0.07] p-4 text-sm text-rose-100">
                <div className="font-semibold">Backend not reachable</div>
                <div className="mt-1 text-rose-100/80">{backendDown}</div>
                <code className="mt-2 block rounded-lg bg-black/40 p-2 font-mono text-xs">cd backend &amp;&amp; uvicorn app.main:app --reload --port 8000</code>
              </div>
            )}
            {page === "dashboard" && <Dashboard />}
            {page === "upload" && <Upload />}
            {page === "editor" && <Editor />}
            {page === "readability" && <Readability />}
            {page === "optimizer" && <Optimizer />}
            {page === "timeline" && <Timeline />}
            {page === "export" && <ExportCentre />}
            {page === "settings" && <SettingsPage />}
          </main>
        </div>
      </div>
      {toast && <Toast message={toast.message} tone={toast.tone} onClose={() => setToast(null)} />}
    </AppContext.Provider>
  );
}
