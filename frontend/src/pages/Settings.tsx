import { CircleCheck, Cpu, KeyRound, Save, SlidersHorizontal, CircleX } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { ThresholdForm } from "../components/ThresholdForm";
import { InfoBanner, PageHeader, Spinner } from "../components/ui";
import { useApp } from "../context";
import type { ModelInfo, Thresholds } from "../types";

export default function SettingsPage() {
  const { settings, setSettings, notify, episode, selectEpisode } = useApp();
  const [model, setModel] = useState(settings?.model ?? "");
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [modelsErr, setModelsErr] = useState<string | null>(null);
  const [saving, setSaving] = useState<null | "model" | "th">(null);
  useEffect(() => { if (settings) setModel(settings.model); }, [settings]);

  if (!settings) return <div className="flex items-center gap-2 text-white/60"><Spinner /> Loading settings…</div>;

  const saveModel = async () => {
    setSaving("model");
    try { setSettings(await api.saveSettings({ model })); notify(`Model set to ${model}.`); }
    catch (e) { notify((e as Error).message, "error"); }
    finally { setSaving(null); }
  };
  const saveTh = async (t: Thresholds) => {
    setSaving("th");
    try {
      setSettings(await api.saveSettings({ thresholds: t }));
      if (episode) selectEpisode(episode.id);
      notify("Thresholds saved — all checks recalculated.");
    } catch (e) { notify((e as Error).message, "error"); }
    finally { setSaving(null); }
  };
  const loadModels = async () => {
    setModelsErr(null);
    try { setModels(await api.models()); } catch (e) { setModelsErr((e as Error).message); }
  };

  return (
    <>
      <PageHeader eyebrow="System" title="Settings" subtitle="AI model selection and the editorial thresholds used by every readability check." />

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card p-5">
          <h3 className="mb-3 flex items-center gap-2 font-display font-semibold"><KeyRound size={16} className="text-cyan-300" /> OpenRouter connection</h3>
          <div className="flex items-center gap-2 text-sm">
            {settings.ai.api_key_configured
              ? <><CircleCheck size={16} className="text-emerald-400" /> API key detected on the backend.</>
              : <><CircleX size={16} className="text-amber-300" /> No API key found on the backend.</>}
          </div>
          <div className="mt-2 font-mono text-xs text-white/45">{settings.ai.base_url}</div>
          <p className="mt-3 text-xs leading-5 text-white/50">The key is read from the <code>OPENROUTER_API_KEY</code> environment variable (or <code>backend/.env</code>) and never sent to the browser. Restart the backend after changing it.</p>
        </div>
        <div className="card p-5">
          <h3 className="mb-3 flex items-center gap-2 font-display font-semibold"><Cpu size={16} className="text-violet-300" /> Default model</h3>
          <input className="input font-mono text-sm" list="settings-models" value={model} onChange={(e) => setModel(e.target.value.trim())} aria-label="Default model" />
          <datalist id="settings-models">{models?.map((m) => <option key={m.id} value={m.id}>{m.free ? "free · " : ""}{m.name}</option>)}</datalist>
          <div className="mt-3 flex flex-wrap gap-2">
            <button className="btn-primary" disabled={!model || model === settings.model || saving === "model"} onClick={() => void saveModel()}>{saving === "model" ? <Spinner /> : <Save size={15} />} Save model</button>
            <button className="btn-ghost" onClick={() => void loadModels()}>Load model list from OpenRouter</button>
            <button className="btn-ghost" onClick={() => setModel("openrouter/free")}>Use openrouter/free</button>
          </div>
          {models && <div className="mt-2 text-xs text-white/45">{models.length} models loaded ({models.filter((m) => m.free).length} free). Start typing to search.</div>}
          {modelsErr && <div className="mt-2 text-xs text-rose-300">{modelsErr}</div>}
        </div>
      </div>

      <div className="card mt-4 p-5">
        <h3 className="mb-1 flex items-center gap-2 font-display font-semibold"><SlidersHorizontal size={16} className="text-cyan-300" /> Editorial thresholds</h3>
        <p className="mb-4 text-xs text-white/50">Applied instantly to every episode. Splitting of new uploads uses “max characters per card”.</p>
        <InfoBanner>These are <b>editorial guidelines, not universal standards</b>. Streaming platforms, broadcasters, languages and audiences all use different limits — set values that match your house style or your distributor's delivery spec.</InfoBanner>
        <ThresholdForm value={settings.thresholds} onSave={(t) => void saveTh(t)} saving={saving === "th"} />
      </div>
    </>
  );
}
