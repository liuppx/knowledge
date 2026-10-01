import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  productionApi,
  type CandidateAcceptRequest,
  type CandidateRejectRequest,
  type EvidenceFilters,
  type ManualItemCreateRequest,
  type ManualItemUpdateRequest,
  type Scope,
} from "../endpoints/production";
import { kbKeys } from "./kbs";
import { sourceKeys } from "./sources";

export const productionKeys = {
  evidence: (kbId: number, filters: EvidenceFilters = {}) => ["kbs", kbId, "evidence", filters] as const,
  evidenceDetail: (kbId: number, evidenceId: number) => ["kbs", kbId, "evidence", "detail", evidenceId] as const,
  candidates: (kbId: number) => ["kbs", kbId, "candidates"] as const,
  items: (kbId: number) => ["kbs", kbId, "items"] as const,
  item: (kbId: number, itemId: number) => ["kbs", kbId, "items", itemId] as const,
};

export function useEvidenceQuery(kbId: number, filters: EvidenceFilters = {}) {
  return useQuery({ queryKey: productionKeys.evidence(kbId, filters), queryFn: () => productionApi.evidence.list(kbId, filters) });
}

export function useEvidenceDetailQuery(kbId: number, evidenceId: number | null) {
  return useQuery({
    queryKey: productionKeys.evidenceDetail(kbId, evidenceId ?? 0),
    queryFn: () => productionApi.evidence.get(kbId, evidenceId as number),
    enabled: evidenceId !== null,
  });
}

export function useCandidatesQuery(kbId: number) {
  return useQuery({ queryKey: productionKeys.candidates(kbId), queryFn: () => productionApi.candidates.list(kbId) });
}

export function useItemsQuery(kbId: number) {
  return useQuery({ queryKey: productionKeys.items(kbId), queryFn: () => productionApi.items.list(kbId) });
}

export function useItemQuery(kbId: number, itemId: number | null) {
  return useQuery({ queryKey: productionKeys.item(kbId, itemId ?? 0), queryFn: () => productionApi.items.get(kbId, itemId as number), enabled: itemId !== null });
}

function useInvalidate(kbId: number) {
  const client = useQueryClient();
  return {
    evidence: () => {
      void client.invalidateQueries({ queryKey: ["kbs", kbId, "evidence"] });
      void client.invalidateQueries({ queryKey: sourceKeys.allAssets(kbId) });
    },
    candidates: () => client.invalidateQueries({ queryKey: productionKeys.candidates(kbId) }),
    items: () => {
      void client.invalidateQueries({ queryKey: productionKeys.items(kbId) });
      void client.invalidateQueries({ queryKey: kbKeys.workbench(kbId) });
    },
  };
}

export function useBuildEvidenceMutation(kbId: number) {
  const invalidate = useInvalidate(kbId);
  return useMutation({ mutationFn: (scope: Scope) => productionApi.evidence.build(kbId, scope), onSuccess: invalidate.evidence });
}

export function useReindexUnitsMutation(kbId: number) {
  return useMutation({ mutationFn: () => productionApi.evidence.reindexUnits(kbId) });
}

export function useGenerateCandidatesMutation(kbId: number) {
  const invalidate = useInvalidate(kbId);
  return useMutation({ mutationFn: (scope: Scope) => productionApi.candidates.generate(kbId, scope), onSuccess: invalidate.candidates });
}

export function useAcceptCandidateMutation(kbId: number) {
  const invalidate = useInvalidate(kbId);
  return useMutation({
    mutationFn: ({ candidateId, payload }: { candidateId: number; payload: CandidateAcceptRequest }) => productionApi.candidates.accept(kbId, candidateId, payload),
    onSuccess: () => {
      void invalidate.candidates();
      invalidate.items();
    },
  });
}

export function useRejectCandidateMutation(kbId: number) {
  const invalidate = useInvalidate(kbId);
  return useMutation({
    mutationFn: ({ candidateId, payload }: { candidateId: number; payload: CandidateRejectRequest }) => productionApi.candidates.reject(kbId, candidateId, payload),
    onSuccess: invalidate.candidates,
  });
}

export function useCreateManualItemMutation(kbId: number) {
  const invalidate = useInvalidate(kbId);
  return useMutation({ mutationFn: (payload: ManualItemCreateRequest) => productionApi.items.createManual(kbId, payload), onSuccess: invalidate.items });
}

export function useUpdateItemMutation(kbId: number) {
  const client = useQueryClient();
  const invalidate = useInvalidate(kbId);
  return useMutation({
    mutationFn: ({ itemId, payload }: { itemId: number; payload: ManualItemUpdateRequest }) => productionApi.items.update(kbId, itemId, payload),
    onSuccess: (_detail, { itemId }) => {
      invalidate.items();
      void client.invalidateQueries({ queryKey: productionKeys.item(kbId, itemId) });
    },
  });
}
