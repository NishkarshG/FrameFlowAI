import type { AIRun, DashboardData, Episode, ModelInfo, Project, SampleFile, Settings, Thresholds } from "./types";

const BASE: string = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  status: number;
  extra: Record<string, unknown>;
  constructor(status: number, message: string, extra: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.extra = extra;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError(0, "Cannot reach the FrameFlow backend. Is it running on port 8000? (uvicorn app.main:app --port 8000)");
  }
  const text = await res.text();
  let body: unknown = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (!res.ok) {
    const b = (body ?? {}) as Record<string, unknown>;
    let msg = typeof b.detail === "string" ? b.detail : `Request failed (HTTP ${res.status})`;
    if (Array.isArray(b.detail)) {
      msg = b.detail.map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(-1)[0] ?? ""}: ${d.msg ?? ""}`).join("; ");
    }
    throw new ApiError(res.status, msg, b);
  }
  return body as T;
}

const json = (method: string, data?: unknown): RequestInit => ({
  method, headers: { "Content-Type": "application/json" }, body: data === undefined ? undefined : JSON.stringify(data),
});

export const api = {
  health: () => request<{ status: string; ai: Settings["ai"]; model: string }>("/api/health"),
  settings: () => request<Settings>("/api/settings"),
  saveSettings: (s: { model?: string; thresholds?: Thresholds }) => request<Settings>("/api/settings", json("PUT", s)),
  models: () => request<ModelInfo[]>("/api/models"),
  dashboard: () => request<DashboardData>("/api/dashboard"),
  samples: () => request<SampleFile[]>("/api/samples"),
  createSample: () => request<Project>("/api/projects/sample", { method: "POST" }),
  createProject: (name: string, files: File[]) => {
    const fd = new FormData();
    fd.append("name", name);
    files.forEach((f) => fd.append("files", f, f.name));
    return request<Project>("/api/projects", { method: "POST", body: fd });
  },
  projects: () => request<Project[]>("/api/projects"),
  deleteProject: (id: string) => request<{ deleted: string }>(`/api/projects/${id}`, { method: "DELETE" }),
  episode: (id: string) => request<Episode>(`/api/episodes/${id}`),
  updateSegment: (eid: string, sid: string, body: { text?: string; start?: string; end?: string }) =>
    request<Episode>(`/api/episodes/${eid}/segments/${sid}`, json("PATCH", body)),
  resplit: (eid: string) => request<Episode>(`/api/episodes/${eid}/resplit`, { method: "POST" }),
  optimize: (eid: string, segment_ids?: string[], model?: string) =>
    request<Episode>(`/api/episodes/${eid}/optimize`, json("POST", { segment_ids, model })),
  aiSegment: (eid: string, model?: string) => request<Episode>(`/api/episodes/${eid}/ai-segment`, json("POST", { model })),
  suggestion: (eid: string, sid: string, action: "accept" | "reject", text?: string) =>
    request<Episode>(`/api/episodes/${eid}/segments/${sid}/suggestion`, json("POST", { action, text })),
  aiRuns: (eid: string) => request<AIRun[]>(`/api/episodes/${eid}/ai-runs`),
  exportText: async (path: string) => {
    const res = await fetch(`${BASE}${path}`);
    if (!res.ok) throw new ApiError(res.status, `Export failed (HTTP ${res.status})`);
    return { text: await res.text(), skipped: Number(res.headers.get("X-Skipped-Segments") ?? 0) };
  },
};

/** Download a file from the API, honouring the server-provided filename. */
export async function download(path: string): Promise<{ filename: string; skipped: number }> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`);
  } catch {
    throw new ApiError(0, "Cannot reach the backend.");
  }
  if (!res.ok) {
    let msg = `Download failed (HTTP ${res.status})`;
    try { msg = (await res.json()).detail ?? msg; } catch { /* ignore */ }
    throw new ApiError(res.status, msg);
  }
  const cd = res.headers.get("Content-Disposition") ?? "";
  const filename = /filename="?([^";]+)"?/.exec(cd)?.[1] ?? "download";
  const skipped = Number(res.headers.get("X-Skipped-Segments") ?? 0);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  return { filename, skipped };
}
