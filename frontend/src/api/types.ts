// Answers of the Graphora service (specs 004, 005, 010, 013, 014, 018, 019 contracts).
import type { Edge } from "./graph.gen";

export type { Edge, GraphoraGraphDocument as GraphDocument } from "./graph.gen";

export type LinkConfidence = "resolved" | "heuristic";

export interface Link {
  source: string;
  target: string;
  confidence: LinkConfidence;
  type_only: boolean;
  edges: Edge[];
  via: Edge[];
  declared?: Edge[];
}

export interface Item {
  node: string;
  kind: string;
  confidence: LinkConfidence;
  type_only: boolean;
  chain: Link[];
  distance?: number;
  transitive_dependents?: number;
  direct_dependents?: number;
  declared_only?: boolean;
  commits?: number;
  authors?: number;
  score?: number;
}

export interface Completeness {
  unresolved_imports: number;
  not_analyzed_files: number;
  files_with_errors: number;
}

export interface CycleCut {
  method: "exact" | "greedy";
  links: Link[];
}

export interface CycleGroup {
  files: string[];
  cycle: Link[];
  type_only: boolean;
  confidence: LinkConfidence;
  suggested_cut?: CycleCut;
}

export interface DefinitionMatch {
  file: string;
  path: string;
  line: number;
  kind: string;
  name: string;
  exported_as?: string[];
}

export interface Component {
  id: string;
  name: string;
  files: string[];
  file_count: number;
  has_cycle: boolean;
}

export interface ComponentLink {
  source: string;
  target: string;
  imports: number;
  heuristic: number;
  in_cycle: boolean;
}

export interface History {
  status: "available" | "partial" | "not_available";
  reason: string | null;
  commit: string | null;
  window_start: string | null;
  newest: string | null;
  oldest: string | null;
  commits_read: number;
  merges_skipped: number;
  shallow_skipped: number;
  local_changes: boolean;
}

export interface Answer {
  snapshot: string;
  question: string;
  target: string | null;
  options: Record<string, unknown>;
  total: number;
  truncated: boolean;
  items?: Item[];
  incoming?: Item[];
  outgoing?: Item[];
  unresolved?: Edge[];
  groups?: CycleGroup[];
  cut?: boolean;
  completeness?: Completeness;
  definitions?: DefinitionMatch[];
  projects?: unknown[];
  history?: History;
  components?: Component[];
  links?: ComponentLink[];
}

export interface Overview {
  snapshot: string;
  schema_version: number;
  extractors: Record<string, string>;
  languages: Record<string, number>;
  files: Record<string, number>;
  nodes: Record<string, number>;
  edges: number;
  unresolved_imports: number;
  history?: History;
}

export interface Repositories {
  repositories: { name: string; snapshots: string[] }[];
}

export interface FileLines {
  path: string;
  has_text: boolean;
  line_count: number;
  start: number;
  end: number;
  lines: { n: number; text: string }[];
}

export interface Files {
  repository: string;
  snapshot: string;
  files: { path: string; has_text: boolean; line_count: number }[];
}

export interface Limits {
  max_files: number;
  max_bytes: number;
  max_seconds: number;
  max_archive_bytes: number;
  max_extract_bytes: number;
  max_entries: number;
  skipped: string[];
}

export interface Info {
  version: string;
  ask: { enabled: boolean; model: string | null };
  jobs: { enabled: boolean; limits: Limits | null };
  mcp_tools: { name: string; description: string }[];
}

export type Stage = "queued" | "resolving" | "fetching" | "analyzing" | "storing" | "done" | "failed";

export interface Job {
  id: string;
  stage: Stage;
  source: { kind: "github" | "zip"; repository: string; ref?: string | null; name?: string };
  limits: Omit<Limits, "skipped">;
  result: {
    action: string;
    repository: string;
    snapshot: string;
    files: number;
    edges: number;
    unresolved: number;
    warnings: string[];
  } | null;
  error: { kind: string; message: string } | null;
}

export interface TraceEvent {
  n: number;
  kind: string;
  role: string;
  tool?: string;
  args?: Record<string, unknown>;
  citation_ids?: string[];
  cut?: boolean;
  error?: string;
  key?: string;
  cite?: string;
  status?: string;
  reason?: string;
  hint?: string;
  detail?: string;
  [extra: string]: unknown;
}

export interface ClaimStep {
  path: string;
  line?: number;
  name?: string;
  target?: string;
}

export interface AnswerPart {
  cite: string;
  text: string;
  reason?: string;
  claim: { kind: string; snapshot: string; statement: string; steps?: ClaimStep[]; [extra: string]: unknown };
}

export interface AgentAnswer {
  question: string;
  snapshot: string;
  summary: string;
  summary_source: string;
  end: string;
  counts: { model_calls: number; revisions: number; tool_calls: number };
  facts: AnswerPart[];
  likely: AnswerPart[];
  hypotheses: AnswerPart[];
}

export interface AskResult {
  answer: AgentAnswer;
  trace: TraceEvent[];
}
