import { useEffect } from "react";
import { Navigate, Outlet, useParams } from "react-router-dom";

import { readLastKbId, rememberKbId } from "./lastKb";

export function parseKbId(raw: string | undefined): number | null {
  const value = Number(raw);
  return Number.isInteger(value) && value > 0 ? value : null;
}

/** Typed access to the KB in the URL. Only valid under the /kbs/:kbId subtree. */
export function useKbId(): number {
  const kbId = parseKbId(useParams().kbId);
  if (kbId === null) throw new Error("useKbId used outside /kbs/:kbId");
  return kbId;
}

/** Validates :kbId, remembers it for the `/` redirect, and renders the section. */
export function KbLayout() {
  const kbId = parseKbId(useParams().kbId);
  useEffect(() => {
    if (kbId !== null) rememberKbId(kbId);
  }, [kbId]);
  if (kbId === null) return <Navigate to="/kbs" replace />;
  return <Outlet key={kbId} />;
}

/** `/` → last used KB overview, else the KB list. */
export function RootRedirect() {
  const lastKbId = readLastKbId();
  return <Navigate to={lastKbId ? `/kbs/${lastKbId}/overview` : "/kbs"} replace />;
}
