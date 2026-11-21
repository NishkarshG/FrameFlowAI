export type Page = "dashboard" | "upload" | "editor" | "readability" | "optimizer" | "timeline" | "export" | "settings";

export interface Thresholds {
  max_chars_per_line: number;
  max_lines: number;
  max_chars_per_segment: number;
  max_cps: number;
  min_duration_s: number;
  max_duration_s: number;
  long_word_chars: number;
  max_words_per_sentence: number;
}

export interface AIStatus { api_key_configured: boolean; base_url: string }
export interface Settings { model: string; thresholds: Thresholds; ai: AIStatus }

export interface EpisodeSummary {
  id: string; name: string; filename: string; is_synthetic: boolean;
  segment_count: number; dialogue_count: number; issue_count: number; error_count: number;
  average_score: number | null; missing_timing: number; pending_suggestions: number;
  created_at: string; updated_at: string;
}

export interface Project { id: string; name: string; is_synthetic: boolean; created_at: string; episodes: EpisodeSummary[] }

export interface Suggestion {
  text: string; rationale: string; preserved_details: string[]; guard_warnings: string[];
  model: string; run_id: string | null; status: "pending" | "accepted" | "rejected";
}

export interface Segment {
  id: string; index: number; line_index: number; character: string; parenthetical: string | null;
  text: string; original_text: string; start_ms: number | null; end_ms: number | null;
  timing_source: "original" | "derived_split" | "manual" | "missing";
  source_line: number; edited: boolean; split_method: "deterministic" | "ai"; suggestion: Suggestion | null;
}

export type Severity = "error" | "warning" | "info";
export interface Issue { code: string; severity: Severity; message: string; value: number | null; threshold: number | null }
export interface SegmentReport {
  segment_id: string;
  metrics: { chars: number; lines: string[]; line_count: number; longest_line: number; duration_s: number | null; cps: number | null; words: number };
  issues: Issue[]; score: number; status: "good" | "warning" | "error";
}
export interface ReadabilityReport {
  segments: Record<string, SegmentReport>; total_segments: number; issue_count: number; error_count: number;
  warning_count: number; issue_breakdown: Record<string, number>; average_score: number | null; disclaimer: string;
}

export interface DialogueLine {
  index: number; character: string; parenthetical: string | null; text: string; start_ms: number | null; end_ms: number | null;
  timing_status: "ok" | "missing" | "missing_end" | "invalid"; source_line: number; scene: string | null;
}

export interface Episode {
  id: string; project_id: string; project_name: string; name: string; filename: string; is_synthetic: boolean;
  raw_text: string; warnings: string[]; characters: string[]; dialogue: DialogueLine[]; segments: Segment[];
  report: ReadabilityReport; thresholds: Thresholds; created_at: string; updated_at: string;
  ai_result?: { run_id: string; model: string; suggested?: number; accepted?: number; rejected: { id: string; reason: string }[] };
}

export interface AIRun {
  id: string; episode_id: string | null; kind: string; model: string; status: string; error: string | null;
  request: unknown; raw_output: string | null; parsed: unknown; created_at: string;
}

export interface DashboardData {
  total_projects: number; total_episodes: number; synthetic_episodes: number; total_segments: number;
  readability_issues: number; readability_errors: number; average_score: number | null; missing_timing: number;
  ai_runs: { success: number; failed: number }; issue_breakdown: Record<string, number>;
  score_distribution: Record<string, number>;
  activity: { date: string; episodes: number; ai_success: number; ai_failed: number; edits: number }[];
  recent_projects: { id: string; name: string; is_synthetic: boolean; created_at: string; episode_count: number; segment_count: number; issue_count: number; average_score: number | null; first_episode_id: string | null }[];
  thresholds: Thresholds;
}

export interface SampleFile { filename: string; content: string; synthetic: boolean }
export interface ModelInfo { id: string; name: string; free: boolean; context_length: number | null }
