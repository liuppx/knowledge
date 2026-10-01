import { request } from "../client";
import type { Schema } from "../types";

export type KnowledgeBase = Schema<"KBResponse">;
export type KBCreateRequest = Schema<"KBCreateRequest">;
export type KBUpdateRequest = Schema<"KBUpdateRequest">;
export type KBStats = Schema<"KBStatsResponse">;
export type KBWorkbench = Schema<"KBWorkbenchResponse">;

export const kbsApi = {
  list: () => request<KnowledgeBase[]>("/kbs"),
  get: (kbId: number) => request<KnowledgeBase>(`/kbs/${kbId}`),
  create: (payload: KBCreateRequest) => request<KnowledgeBase>("/kbs", { method: "POST", json: payload }),
  update: (kbId: number, payload: KBUpdateRequest) => request<KnowledgeBase>(`/kbs/${kbId}`, { method: "PATCH", json: payload }),
  remove: (kbId: number) => request<unknown>(`/kbs/${kbId}`, { method: "DELETE" }),
  stats: (kbId: number) => request<KBStats>(`/kbs/${kbId}/stats`),
  workbench: (kbId: number) => request<KBWorkbench>(`/kbs/${kbId}/workbench`),
};
