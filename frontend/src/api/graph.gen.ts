// generated from schema/graph.schema.json by npm run gen:types

export type Snapshot = string;
export type Node = FileNode | ExternalNode | UnresolvedNode | AssetNode | ProjectNode | SolutionNode;
export type FileNode = {
  id: string;
  kind: "file";
  path: Relpath;
  language: "python" | "typescript" | "javascript" | "csharp";
  definitions: Definition[];
  exports?: Export[];
  project?: string | null;
};
export type Relpath = string;
export type ExternalNode = {
  id: string;
  kind: "external";
  name: string;
  ecosystem: Ecosystem;
  category: "stdlib" | "builtin" | "third_party";
};
export type Ecosystem = "python" | "npm" | "dotnet" | "nuget";
export type UnresolvedNode = {
  id: string;
  kind: "unresolved";
  reference: string;
  ecosystem: "python" | "npm" | "dotnet" | "http";
};
export type Edge = {
  id: string;
  source: string;
  target: string;
  type:
    | "imports"
    | "reexports"
    | "project_reference"
    | "package_reference"
    | "type_reference"
    | "solution_member"
    | "http_call";
  form: "static" | "dynamic" | "require";
  type_only: boolean;
  symbol: string | null;
  alias?: string;
  line: number;
  column: number;
  route_line?: number;
  snapshot: Snapshot;
  confidence: "resolved" | "heuristic" | "unresolved";
  reason?:
    | "not_found"
    | "relative_beyond_top"
    | "namespace_package"
    | "dynamic"
    | "workspace_package"
    | "not_referenced"
    | "no_types"
    | "ambiguous"
    | "msbuild_property"
    | "namespace_spread"
    | "partial_type"
    | "package_prefix"
    | "msbuild_condition"
    | "not_csharp"
    | "http_route";
  extractor: string;
  snippet_hash: string;
  directive?: "using" | "using_static" | "using_alias";
  global_using?: boolean;
};
export type CoverageFile = {
  path: Relpath;
  language: string | null;
  status: "analyzed" | "detected_only" | "not_code";
  flags: ("parse_error" | "unreadable" | "ambiguous_project")[];
  unresolved_type_names?: number;
};

/**
 * Schema version 9. Commit-pinned dependency graph with provenance on every edge. Python, TypeScript, JavaScript and C#.
 */
export interface GraphoraGraphDocument {
  schema_version: 9;
  snapshot: Snapshot;
  extractors: {
    [k: string]: string;
  };
  nodes: Node[];
  edges: Edge[];
  coverage: Coverage;
  history: History;
}
export interface Definition {
  kind: "class" | "function" | "method" | "interface" | "type_alias" | "enum" | "struct" | "record" | "delegate";
  name: string;
  line: number;
  exported_as?: string[];
}
export interface Export {
  name: string;
  local: string | null;
  line: number;
}
export interface AssetNode {
  id: string;
  kind: "asset";
  path: Relpath;
}
export interface ProjectNode {
  id: string;
  kind: "project";
  path: Relpath;
}
export interface SolutionNode {
  id: string;
  kind: "solution";
  path: Relpath;
}
export interface Coverage {
  files: CoverageFile[];
  skipped: Skipped[];
  summary: {
    analyzed: number;
    detected_only: number;
    not_code: number;
    skipped: number;
    by_language: {
      [k: string]: number;
    };
  };
}
export interface Skipped {
  path: Relpath;
  reason: "excluded_dir" | "nested_repository" | "symlink" | "minified" | "unreadable_dir";
}
/**
 * Counts from the git history of the snapshot commit (specs/014-hotspots). No author names or e-mail addresses.
 */
export interface History {
  status: "available" | "partial" | "not_available";
  reason:
    | null
    | ("no_git" | "zip" | "unreadable" | "skipped" | "fetch_failed" | "too_large" | "time_limit" | "not_collected");
  commit: null | string;
  window_start: null | string;
  newest: null | string;
  oldest: null | string;
  commits_read: number;
  merges_skipped: number;
  shallow_skipped: number;
  local_changes: boolean;
  files: {
    path: Relpath;
    commits: number;
    authors: number;
  }[];
}
