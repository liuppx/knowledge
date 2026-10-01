import { request } from "../client";
import type { Schema } from "../types";

export type Source = Schema<"SourceRead">;
export type SourceCreateRequest = Schema<"SourceCreateRequest">;
export type SourceUpdateRequest = Schema<"SourceUpdateRequest">;
export type SourceScanResponse = Schema<"SourceScanResponse">;
export type SourceAsset = Schema<"SourceAssetRead">;

export const SOURCE_TYPES = [
  { value: "warehouse", label: "Warehouse 文件或目录", placeholder: "/apps/knowledge.yeying.pub/uploads" },
  { value: "local_file", label: "本地目录（测试用）", placeholder: "例如 docs" },
  { value: "github_repository", label: "GitHub 仓库", placeholder: "owner/repository@main:docs" },
] as const;

export const sourcesApi = {
  list: (kbId: number) => request<Source[]>(`/kbs/${kbId}/sources`),
  get: (kbId: number, sourceId: number) => request<Source>(`/kbs/${kbId}/sources/${sourceId}`),
  create: (kbId: number, payload: SourceCreateRequest) => request<Source>(`/kbs/${kbId}/sources`, { method: "POST", json: payload }),
  update: (kbId: number, sourceId: number, payload: SourceUpdateRequest) =>
    request<Source>(`/kbs/${kbId}/sources/${sourceId}`, { method: "PATCH", json: payload }),
  scan: (kbId: number, sourceId: number) => request<SourceScanResponse>(`/kbs/${kbId}/sources/${sourceId}/scan`, { method: "POST" }),
  assets: (kbId: number, sourceId: number) => request<SourceAsset[]>(`/kbs/${kbId}/sources/${sourceId}/assets`),
  allAssets: (kbId: number) => request<SourceAsset[]>(`/kbs/${kbId}/assets`),
};
