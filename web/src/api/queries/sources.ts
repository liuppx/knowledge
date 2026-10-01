import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { sourcesApi, type SourceCreateRequest, type SourceUpdateRequest } from "../endpoints/sources";
import { kbKeys } from "./kbs";

export const sourceKeys = {
  list: (kbId: number) => ["kbs", kbId, "sources"] as const,
  assets: (kbId: number, sourceId: number) => ["kbs", kbId, "sources", sourceId, "assets"] as const,
  allAssets: (kbId: number) => ["kbs", kbId, "assets"] as const,
};

export function useSourcesQuery(kbId: number) {
  return useQuery({ queryKey: sourceKeys.list(kbId), queryFn: () => sourcesApi.list(kbId) });
}

export function useSourceAssetsQuery(kbId: number, sourceId: number | null) {
  return useQuery({
    queryKey: sourceKeys.assets(kbId, sourceId ?? 0),
    queryFn: () => sourcesApi.assets(kbId, sourceId as number),
    enabled: sourceId !== null,
  });
}

export function useAllAssetsQuery(kbId: number) {
  return useQuery({ queryKey: sourceKeys.allAssets(kbId), queryFn: () => sourcesApi.allAssets(kbId) });
}

export function useInvalidateSources(kbId: number) {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: sourceKeys.list(kbId) });
    void client.invalidateQueries({ queryKey: sourceKeys.allAssets(kbId) });
    void client.invalidateQueries({ queryKey: kbKeys.workbench(kbId) });
  };
}

export function useCreateSourceMutation(kbId: number) {
  const invalidate = useInvalidateSources(kbId);
  return useMutation({ mutationFn: (payload: SourceCreateRequest) => sourcesApi.create(kbId, payload), onSuccess: invalidate });
}

export function useUpdateSourceMutation(kbId: number) {
  const invalidate = useInvalidateSources(kbId);
  return useMutation({
    mutationFn: ({ sourceId, payload }: { sourceId: number; payload: SourceUpdateRequest }) => sourcesApi.update(kbId, sourceId, payload),
    onSuccess: invalidate,
  });
}

export function useScanSourceMutation(kbId: number) {
  const client = useQueryClient();
  const invalidate = useInvalidateSources(kbId);
  return useMutation({
    mutationFn: (sourceId: number) => sourcesApi.scan(kbId, sourceId),
    onSuccess: (_result, sourceId) => {
      invalidate();
      void client.invalidateQueries({ queryKey: sourceKeys.assets(kbId, sourceId) });
    },
  });
}
