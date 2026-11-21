import { createContext, useContext } from "react";
import type { Episode, Page, Project, Settings } from "./types";

export interface AppState {
  settings: Settings | null;
  setSettings: (s: Settings) => void;
  projects: Project[];
  refreshProjects: () => Promise<Project[]>;
  project: Project | null;
  episode: Episode | null;
  episodeLoading: boolean;
  setEpisode: (e: Episode) => void;
  selectProject: (id: string, episodeId?: string) => void;
  selectEpisode: (id: string) => void;
  go: (page: Page, focusSegmentId?: string) => void;
  focusSegmentId: string | null;
  notify: (message: string, tone?: "success" | "error" | "info") => void;
}

export const AppContext = createContext<AppState | null>(null);

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("AppContext missing");
  return ctx;
}
