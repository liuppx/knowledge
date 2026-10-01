import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { kbsApi, type KBCreateRequest, type KBUpdateRequest } from "../endpoints/kbs";

// Query keys are always prefixed with the KB id so switching KBs never shares cache.
export const kbKeys = {
  all: ["kbs"] as const,
  list: () => ["kbs", "list"] as const,
  detail: (kbId: number) => ["kbs", kbId, "detail"] as const,
  stats: (kbId: number) => ["kbs", kbId, "stats"] as const,
  workbench: (kbId: number) => ["kbs", kbId, "workbench"] as const,
};

export function useKbsQuery() {
  return useQuery({ queryKey: kbKeys.list(), queryFn: kbsApi.list });
}

export function useKbQuery(kbId: number | null) {
  return useQuery({ queryKey: kbKeys.detail(kbId ?? 0), queryFn: () => kbsApi.get(kbId as number), enabled: kbId !== null });
}

export function useKbStatsQuery(kbId: number) {
  return useQuery({ queryKey: kbKeys.stats(kbId), queryFn: () => kbsApi.stats(kbId) });
}

export function useKbWorkbenchQuery(kbId: number) {
  return useQuery({ queryKey: kbKeys.workbench(kbId), queryFn: () => kbsApi.workbench(kbId) });
}

export function useCreateKbMutation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: KBCreateRequest) => kbsApi.create(payload),
    onSuccess: () => client.invalidateQueries({ queryKey: kbKeys.list() }),
  });
}

export function useUpdateKbMutation(kbId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: KBUpdateRequest) => kbsApi.update(kbId, payload),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: kbKeys.list() });
      void client.invalidateQueries({ queryKey: kbKeys.detail(kbId) });
      void client.invalidateQueries({ queryKey: kbKeys.workbench(kbId) });
    },
  });
}

export function useDeleteKbMutation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (kbId: number) => kbsApi.remove(kbId),
    onSuccess: (_result, kbId) => {
      void client.invalidateQueries({ queryKey: kbKeys.list() });
      client.removeQueries({ queryKey: ["kbs", kbId] });
    },
  });
}
