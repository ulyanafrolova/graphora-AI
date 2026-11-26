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
