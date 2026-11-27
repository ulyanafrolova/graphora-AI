import { QueryClient, useQueries, useQuery, type UseQueryResult } from "@tanstack/react-query";

import { ApiError, apiGet, type Params } from "./client";
import type { Answer, Files, FileLines, GraphDocument, Info, Overview, Repositories } from "./types";

const RETRY = new Set(["network", "store_unavailable"]);

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: Infinity,
        refetchOnWindowFocus: false,
        retry: (count, error) => count < 2 && error instanceof ApiError && RETRY.has(error.kind),
      },
    },
  });
}

export interface Snapshot {
  repository: string;
  snapshot: string;
}

function useApi<T>(path: string, params: Params | null): UseQueryResult<T, ApiError> {
  return useQuery<T, ApiError>({
    queryKey: [path, params],
    queryFn: ({ signal }) => apiGet<T>(path, params ?? {}, signal),
    enabled: params !== null,
  });
}

const of = (s: Snapshot | null, more: Params = {}): Params | null => (s === null ? null : { ...s, ...more });

export const useRepositories = () => useApi<Repositories>("repositories", {});
export const useInfo = () => useApi<Info>("info", {});
export const useGraph = (s: Snapshot | null) => useApi<GraphDocument>("graph", of(s));
export const useOverview = (s: Snapshot | null) => useApi<Overview>("overview", of(s));
export const useComponents = (s: Snapshot | null) => useApi<Answer>("components", of(s));
export const useKeyFiles = (s: Snapshot | null) => useApi<Answer>("key_files", of(s, { limit: 500 }));
export const useCycles = (s: Snapshot | null) => useApi<Answer>("cycles", of(s, { limit: 500 }));
export const useHotspots = (s: Snapshot | null) => useApi<Answer>("hotspots", of(s, { limit: 500 }));
export const useFiles = (s: Snapshot | null) => useApi<Files>("files", of(s));

export const useImpact = (s: Snapshot | null, target: string | null) =>
  useApi<Answer>("impact", target === null ? null : of(s, { target, limit: 500 }));
export const useNeighbors = (s: Snapshot | null, target: string | null) =>
  useApi<Answer>("neighbors", target === null ? null : of(s, { target }));
export const useDependencies = (s: Snapshot | null, target: string | null) =>
  useApi<Answer>("dependencies", target === null ? null : of(s, { target, limit: 500 }));
export const useDependents = (s: Snapshot | null, target: string | null) =>
  useApi<Answer>("dependents", target === null ? null : of(s, { target, limit: 500 }));
export const useDefinitions = (s: Snapshot | null, name: string | null) =>
  useApi<Answer>("definitions", name === null || name === "" ? null : of(s, { name }));
export const useFileLines = (s: Snapshot | null, path: string | null) =>
  useApi<FileLines>("file", path === null ? null : of(s, { path }));

/** The text of single lines, keyed "path:line"; "" while a line is on its way or when it cannot be read. */
export function useLineTexts(s: Snapshot, wanted: { path: string; line: number }[]): Map<string, string> {
  const texts = useQueries({
    queries: wanted.map((w) => {
      const params = { ...s, path: w.path, start: w.line, end: w.line };
      return {
        queryKey: ["file", params],
        queryFn: ({ signal }: { signal: AbortSignal }) => apiGet<FileLines>("file", params, signal),
      };
    }),
  });
  return new Map(wanted.map((w, i) => [`${w.path}:${w.line}`, texts[i]?.data?.lines[0]?.text ?? ""]));
}
