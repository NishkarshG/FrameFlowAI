import { RotateCcw, Save } from "lucide-react";
import { useEffect, useState } from "react";
import type { Thresholds } from "../types";
import { Spinner } from "./ui";

export const DEFAULT_THRESHOLDS: Thresholds = {
  max_chars_per_line: 42, max_lines: 2, max_chars_per_segment: 84, max_cps: 17,
  min_duration_s: 1, max_duration_s: 7, long_word_chars: 13, max_words_per_sentence: 18,
};

const FIELDS: { key: keyof Thresholds; label: string; hint: string; step: number }[] = [
  { key: "max_chars_per_line", label: "Max characters per line", hint: "Mobile vertical video often uses 32–42.", step: 1 },
  { key: "max_lines", label: "Max lines per subtitle", hint: "Most guides use 2.", step: 1 },
  { key: "max_chars_per_segment", label: "Max characters per card", hint: "Long lines are split above this.", step: 1 },
  { key: "max_cps", label: "Max reading speed (chars/sec)", hint: "Common range 12–20 cps.", step: 0.5 },
  { key: "min_duration_s", label: "Min duration (s)", hint: "Shorter cards flash by.", step: 0.1 },
  { key: "max_duration_s", label: "Max duration (s)", hint: "Longer cards feel stale.", step: 0.5 },
  { key: "long_word_chars", label: "Difficult word length", hint: "Words this long are flagged (info).", step: 1 },
  { key: "max_words_per_sentence", label: "Max words per sentence", hint: "Longer sentences flagged (info).", step: 1 },
];

export function ThresholdForm({ value, onSave, saving }: { value: Thresholds; onSave: (t: Thresholds) => void; saving?: boolean }) {
  const [draft, setDraft] = useState<Thresholds>(value);
  useEffect(() => setDraft(value), [value]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(value);
  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {FIELDS.map((f) => (
          <label key={f.key} className="block">
            <span className="label">{f.label}</span>
            <input type="number" step={f.step} className="input mt-1.5 font-mono" value={draft[f.key]}
              onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value === "" ? 0 : Number(e.target.value) })} />
            <span className="mt-1 block text-[11px] text-white/40">{f.hint}</span>
          </label>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button className="btn-primary" disabled={!dirty || saving} onClick={() => onSave(draft)}>
          {saving ? <Spinner /> : <Save size={15} />} Save thresholds
        </button>
        <button className="btn-ghost" onClick={() => setDraft(DEFAULT_THRESHOLDS)}><RotateCcw size={15} /> Reset to defaults</button>
      </div>
    </div>
  );
}
