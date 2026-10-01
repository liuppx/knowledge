import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { searchApi, type SearchLabCompareRequest } from "../endpoints/search";

export const searchKeys = {
  logs: (kbId: number) => ["kbs", kbId, "retrieval-logs"] as const,
  log: (kbId: number, logId: number) => ["kbs", kbId, "retrieval-logs", logId] as const,
  governance: (kbId: number) => ["kbs", kbId, "source-governance"] as const,
};

export function useCompareMutation(kbId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: SearchLabCompareRequest) => searchApi.compare(kbId, payload),
    // Every compare writes a retrieval log and may surface new source-health facts.
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: searchKeys.logs(kbId) });
      void client.invalidateQueries({ queryKey: searchKeys.governance(kbId) });
    },
  });
}

export function useRetrievalLogsQuery(kbId: number, limit = 50) {
  return useQuery({ queryKey: [...searchKeys.logs(kbId), limit], queryFn: () => searchApi.retrievalLogs(kbId, limit) });
}

export function useRetrievalLogQuery(kbId: number, logId: number | null) {
  return useQuery({ queryKey: searchKeys.log(kbId, logId ?? 0), queryFn: () => searchApi.retrievalLog(kbId, logId as number), enabled: logId !== null });
}

export function useSourceGovernanceQuery(kbId: number) {
  return useQuery({ queryKey: searchKeys.governance(kbId), queryFn: () => searchApi.sourceGovernance(kbId) });
}
