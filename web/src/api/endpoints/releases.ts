import { ApiError, request } from "../client";
import type { Schema } from "../types";

export type Release = Schema<"KBReleaseRead">;
export type ReleaseItem = Schema<"KBReleaseItemRead">;
export type ReleaseDetail = Schema<"ReleaseDetailResponse">;
export type ReleasePublishRequest = Schema<"ReleasePublishRequest">;
export type ReleaseHotfixRequest = Schema<"ReleaseHotfixRequest">;
export type ReleaseRollbackRequest = Schema<"ReleaseRollbackRequest">;

export const releasesApi = {
  list: (kbId: number) => request<Release[]>(`/kbs/${kbId}/releases`),
  get: (kbId: number, releaseId: number) => request<ReleaseDetail>(`/kbs/${kbId}/releases/${releaseId}`),
  /** `null` when the KB has never been published (backend answers 404). */
  current: async (kbId: number): Promise<ReleaseDetail | null> => {
    try {
      return await request<ReleaseDetail>(`/kbs/${kbId}/releases/current`);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 404) return null;
      throw cause;
    }
  },
  publish: (kbId: number, payload: ReleasePublishRequest) => request<ReleaseDetail>(`/kbs/${kbId}/releases`, { method: "POST", json: payload }),
  hotfix: (kbId: number, releaseId: number, payload: ReleaseHotfixRequest) =>
    request<ReleaseDetail>(`/kbs/${kbId}/releases/${releaseId}/hotfix`, { method: "POST", json: payload }),
  rollback: (kbId: number, releaseId: number, payload: ReleaseRollbackRequest) =>
    request<ReleaseDetail>(`/kbs/${kbId}/releases/${releaseId}/rollback`, { method: "POST", json: payload }),
};
