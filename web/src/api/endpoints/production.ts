import { request } from "../client";
import type { Schema } from "../types";

export type Evidence = Schema<"EvidenceUnitRead">;
export type EvidenceBuildResponse = Schema<"EvidenceBuildResponse">;
export type UnitReindexResponse = Schema<"UnitReindexResponse">;
export type Candidate = Schema<"KnowledgeItemCandidateRead">;
export type CandidateGenerationResponse = Schema<"CandidateGenerationResponse">;
export type CandidateAcceptRequest = Schema<"CandidateAcceptRequest">;
export type CandidateRejectRequest = Schema<"CandidateRejectRequest">;
export type KnowledgeItem = Schema<"KnowledgeItemListRead">;
export type KnowledgeItemDetail = Schema<"KnowledgeItemDetailResponse">;
export type KnowledgeItemRevision = Schema<"KnowledgeItemRevisionDetailRead">;
export type ManualItemCreateRequest = Schema<"ManualItemCreateRequest">;
export type ManualItemUpdateRequest = Schema<"ManualItemUpdateRequest">;

// knowledge/services/item_contracts.py SUPPORTED_ITEM_TYPES
export const ITEM_TYPES = ["fact", "rule", "procedure", "faq", "reference"] as const;
export const ITEM_TYPE_LABELS: Record<string, string> = { fact: "事实", rule: "规则", procedure: "流程", faq: "问答", reference: "参考" };
export const CANDIDATE_REVIEW_STATUSES = ["pending_review", "accepted", "rejected", "merged"] as const;
export const LIFECYCLE_STATUSES = ["candidate", "confirmed", "rejected", "archived"] as const;

export type EvidenceFilters = { source_id?: number | null; asset_id?: number | null; evidence_type?: string | null; vector_status?: string | null };
export type Scope = { kind: "source" | "asset"; id: number };

export const productionApi = {
  evidence: {
    list: (kbId: number, filters: EvidenceFilters = {}) => request<Evidence[]>(`/kbs/${kbId}/evidence`, { query: filters }),
    get: (kbId: number, evidenceId: number) => request<Evidence>(`/kbs/${kbId}/evidence/${evidenceId}`),
    build: (kbId: number, scope: Scope) =>
      request<EvidenceBuildResponse>(`/kbs/${kbId}/${scope.kind === "source" ? "sources" : "assets"}/${scope.id}/build-evidence`, { method: "POST" }),
    reindexUnits: (kbId: number) => request<UnitReindexResponse>(`/kbs/${kbId}/reindex-units`, { method: "POST" }),
  },
  candidates: {
    list: (kbId: number) => request<Candidate[]>(`/kbs/${kbId}/candidates`),
    generate: (kbId: number, scope: Scope) =>
      request<CandidateGenerationResponse>(`/kbs/${kbId}/${scope.kind === "source" ? "sources" : "assets"}/${scope.id}/generate-candidates`, { method: "POST" }),
    accept: (kbId: number, candidateId: number, payload: CandidateAcceptRequest) =>
      request<KnowledgeItemDetail>(`/kbs/${kbId}/candidates/${candidateId}/accept`, { method: "POST", json: payload }),
    reject: (kbId: number, candidateId: number, payload: CandidateRejectRequest) =>
      request<Candidate>(`/kbs/${kbId}/candidates/${candidateId}/reject`, { method: "POST", json: payload }),
  },
  items: {
    list: (kbId: number) => request<KnowledgeItem[]>(`/kbs/${kbId}/items`),
    get: (kbId: number, itemId: number) => request<KnowledgeItemDetail>(`/kbs/${kbId}/items/${itemId}`),
    createManual: (kbId: number, payload: ManualItemCreateRequest) => request<KnowledgeItemDetail>(`/kbs/${kbId}/items/manual`, { method: "POST", json: payload }),
    update: (kbId: number, itemId: number, payload: ManualItemUpdateRequest) =>
      request<KnowledgeItemDetail>(`/kbs/${kbId}/items/${itemId}`, { method: "PATCH", json: payload }),
  },
};
