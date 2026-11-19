import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { kdgApi, type KdgRelationKind, type KdgSettingsUpdateRequest } from "../endpoints/kdg";
import { productionKeys } from "./production";

export const kdgKeys = {
  status: (kbId: number, itemId: number) => ["kbs", kbId, "items", itemId, "kdg"] as const,
};

export function useKdgStatusQuery(kbId: number, itemId: number | null) {
  return useQuery({
    queryKey: kdgKeys.status(kbId, itemId ?? 0),
    queryFn: () => kdgApi.status(kbId, itemId as number),
    enabled: itemId !== null,
  });
}

function useRefresh(kbId: number, itemId: number) {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: kdgKeys.status(kbId, itemId) });
    void client.invalidateQueries({ queryKey: productionKeys.item(kbId, itemId) });
  };
}

export function useKdgSettingsMutation(kbId: number, itemId: number) {
  const refresh = useRefresh(kbId, itemId);
  return useMutation({
    mutationFn: (payload: KdgSettingsUpdateRequest) => kdgApi.updateSettings(kbId, itemId, payload),
    onSuccess: refresh,
  });
}

export function useKdgRelationMutations(kbId: number, itemId: number) {
  const refresh = useRefresh(kbId, itemId);
  const add = useMutation({
    mutationFn: ({ toItemId, kind }: { toItemId: number; kind: KdgRelationKind }) => kdgApi.addRelation(kbId, itemId, toItemId, kind),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (relationId: number) => kdgApi.removeRelation(kbId, itemId, relationId),
    onSuccess: refresh,
  });
  return { add, remove };
}

export { useRefresh as useKdgRefresh };
