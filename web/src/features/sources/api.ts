import { request } from "../../api/client";

export type KnowledgeBase = { id: number; name: string; description: string };
export type Source = { id: number; source_type: string; source_path: string; scope_type: string; sync_status: string; last_synced_at: string | null };
export type Evidence = { id: number; text: string; source_locator: Record<string, unknown> };

export const sourcesApi = {
  listKnowledgeBases: () => request<KnowledgeBase[]>("/kbs"),
  createKnowledgeBase: (name: string) => request<KnowledgeBase>("/kbs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, description: "", retrieval_config: {} }) }),
  listSources: (kbId: number) => request<Source[]>(`/kbs/${kbId}/sources`),
  createSource: (kbId: number, sourceType: string, sourcePath: string) => request<Source>(`/kbs/${kbId}/sources`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_type: sourceType, source_path: sourcePath, scope_type: "directory" }) }),
  scan: (kbId: number, sourceId: number) => request(`/kbs/${kbId}/sources/${sourceId}/scan`, { method: "POST" }),
  buildEvidence: (kbId: number, sourceId: number) => request(`/kbs/${kbId}/sources/${sourceId}/build-evidence`, { method: "POST" }),
  evidence: (kbId: number, sourceId: number) => request<Evidence[]>(`/kbs/${kbId}/evidence?source_id=${sourceId}`),
};
