import { useCallback } from "react";
import { useLocation, useNavigate } from "react-router";

import { parseRoute, toPath, type RouteState } from "./route";

export function useRoute(): RouteState | null {
  const location = useLocation();
  return parseRoute(location.pathname, location.search);
}

export function useGo(): (state: RouteState, replace?: boolean) => void {
  const navigate = useNavigate();
  return useCallback((state, replace = false) => void navigate(toPath(state), { replace }), [navigate]);
}

/** Opens Ask agents for the route's snapshot with the question filled in. */
export function useAsk(): (state: RouteState, question: string) => void {
  const navigate = useNavigate();
  return useCallback(
    (state, question) => void navigate(toPath({ ...state, screen: "ask" }), { state: { question } }),
    [navigate],
  );
}
