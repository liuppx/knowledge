import { request } from "../client";
import type { Schema } from "../types";

// 「上链到知行图」(KnowDoGraph):签名在浏览器里由夜莺钱包完成,后端只准备意图、核对签名、提交。
export type KdgStatus = Schema<"KdgStatusResponse">;
export type KdgPublication = Schema<"KdgPublicationRead">;
export type KdgPrepareResponse = Schema<"KdgPrepareResponse">;
export type KdgSettingsUpdateRequest = Schema<"KdgSettingsUpdateRequest">;
export type KdgRelationKind = "basis" | "see-also" | "supersedes";

export const KDG_LAYERS = ["foundation", "explanation", "scenario", "application"] as const;
export const KDG_LAYER_LABELS: Record<string, string> = { foundation: "基础", explanation: "解释", scenario: "场景", application: "应用" };
export const KDG_RELATION_LABELS: Record<KdgRelationKind, string> = { basis: "依据", "see-also": "参见", supersedes: "取代" };
export const KDG_STATUS_LABELS: Record<string, string> = { prepared: "待签名", submitted: "等待链上确认", confirmed: "已上链", failed: "失败" };

const base = (kbId: number, itemId: number) => `/kbs/${kbId}/items/${itemId}/kdg`;

export const kdgApi = {
  status: (kbId: number, itemId: number) => request<KdgStatus>(base(kbId, itemId)),
  updateSettings: (kbId: number, itemId: number, payload: KdgSettingsUpdateRequest) =>
    request<KdgStatus>(`${base(kbId, itemId)}/settings`, { method: "PUT", json: payload }),
  addRelation: (kbId: number, itemId: number, toItemId: number, kind: KdgRelationKind) =>
    request<KdgStatus>(`${base(kbId, itemId)}/relations`, { method: "POST", json: { to_item_id: toItemId, kind } }),
  removeRelation: (kbId: number, itemId: number, relationId: number) =>
    request<KdgStatus>(`${base(kbId, itemId)}/relations/${relationId}`, { method: "DELETE" }),
  prepare: (kbId: number, itemId: number, pubkey: string) =>
    request<KdgPrepareResponse>(`${base(kbId, itemId)}/prepare`, { method: "POST", json: { pubkey } }),
  submit: (kbId: number, itemId: number, publicationId: number, signed: string, address: string) =>
    request<KdgPublication>(`${base(kbId, itemId)}/publications/${publicationId}/submit`, { method: "POST", json: { signed, address } }),
  refresh: (kbId: number, itemId: number, publicationId: number) =>
    request<KdgPublication>(`${base(kbId, itemId)}/publications/${publicationId}/refresh`, { method: "POST" }),
};
