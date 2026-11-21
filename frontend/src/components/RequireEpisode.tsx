import { FileUp, FlaskConical, Film } from "lucide-react";
import { useState, type ReactNode } from "react";
import { api } from "../api";
import { useApp } from "../context";
import type { Episode } from "../types";
import { EmptyState, Spinner } from "./ui";

export function useLoadDemo() {
  const { refreshProjects, selectProject, notify } = useApp();
  const [loading, setLoading] = useState(false);
  const run = async () => {
    setLoading(true);
    try {
      const p = await api.createSample();
      await refreshProjects();
      selectProject(p.id, p.episodes[0]?.id);
      notify(`Synthetic demo loaded: ${p.episodes.length} episodes analysed.`);
      return p;
    } catch (e) {
      notify((e as Error).message, "error");
    } finally {
      setLoading(false);
    }
  };
  return { loading, run };
}

export function RequireEpisode({ children }: { children: (ep: Episode) => ReactNode }) {
  const { episode, episodeLoading, go } = useApp();
  const demo = useLoadDemo();
  if (episode) return <>{children(episode)}</>;
  if (episodeLoading) return <div className="flex items-center gap-2 text-white/60"><Spinner /> Loading episode…</div>;
  return (
    <EmptyState icon={<Film size={24} />} title="No episode selected"
      body="Upload a TXT screenplay or load the clearly labelled synthetic demo to start working on subtitles."
      action={<>
        <button className="btn-primary" onClick={() => go("upload")}><FileUp size={15} /> Upload screenplay</button>
        <button className="btn-ghost" onClick={() => void demo.run()} disabled={demo.loading}>
          {demo.loading ? <Spinner /> : <FlaskConical size={15} />} Load synthetic demo
        </button>
      </>} />
  );
}
