import { request } from "../client";
import type { Schema } from "../types";

export type SearchLabCompareRequest = Schema<"SearchLabCompareRequest">;
export type SearchLabCompareResponse = Schema<"SearchLabCompareResponse">;
export type ServiceSearchResponse = Schema<"ServiceSearchResponse">;
export type SearchHit = Schema<"ServiceSearchHit">;
export type RetrievalLog = Schema<"RetrievalLogRead">;
export type SourceGovernance = Schema<"SourceGovernanceResponse">;

export const RESULT_VIEWS = ["compact", "referenced", "audit"] as const;
export const AVAILABILITY_MODES = [
  { value: "allow_all", label: "全部来源" },
  { value: "healthy_only", label: "仅健康来源" },
  { value: "exclude_source_missing", label: "排除来源缺失" },
] as const;
export const SEARCH_MODES = [
  { key: "formal_first", label: "Formal first", description: "先正式知识，不足再补 Evidence（消费方默认）" },
  { key: "formal_only", label: "Formal only", description: "仅已发布的正式知识项" },
  { key: "evidence_only", label: "Evidence only", description: "仅证据单元" },
] as const;

export const searchApi = {
  compare: (kbId: number, payload: SearchLabCompareRequest) => request<SearchLabCompareResponse>(`/kbs/${kbId}/search-lab/compare`, { method: "POST", json: payload }),
  retrievalLogs: (kbId: number, limit = 50) => request<RetrievalLog[]>(`/kbs/${kbId}/retrieval-logs`, { query: { limit } }),
  retrievalLog: (kbId: number, logId: number) => request<RetrievalLog>(`/kbs/${kbId}/retrieval-logs/${logId}`),
  sourceGovernance: (kbId: number) => request<SourceGovernance>(`/kbs/${kbId}/source-governance`),
};
