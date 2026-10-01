import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { grantsApi, type ServiceGrantCreateRequest, type ServiceGrantUpdateRequest, type ServicePrincipalCreateRequest, type ServicePrincipalUpdateRequest } from "../endpoints/grants";

export const grantKeys = {
  principals: ["service-principals"] as const,
  grants: (kbId: number) => ["kbs", kbId, "grants"] as const,
};

export function usePrincipalsQuery() {
  return useQuery({ queryKey: grantKeys.principals, queryFn: grantsApi.principals.list });
}

export function useGrantsQuery(kbId: number) {
  return useQuery({ queryKey: grantKeys.grants(kbId), queryFn: () => grantsApi.grants.list(kbId) });
}

export function useCreatePrincipalMutation() {
  const client = useQueryClient();
  return useMutation({ mutationFn: (payload: ServicePrincipalCreateRequest) => grantsApi.principals.create(payload), onSuccess: () => client.invalidateQueries({ queryKey: grantKeys.principals }) });
}

export function useUpdatePrincipalMutation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ principalId, payload }: { principalId: number; payload: ServicePrincipalUpdateRequest }) => grantsApi.principals.update(principalId, payload),
    onSuccess: () => client.invalidateQueries({ queryKey: grantKeys.principals }),
  });
}

export function useCreateGrantMutation(kbId: number) {
  const client = useQueryClient();
  return useMutation({ mutationFn: (payload: ServiceGrantCreateRequest) => grantsApi.grants.create(kbId, payload), onSuccess: () => client.invalidateQueries({ queryKey: grantKeys.grants(kbId) }) });
}

export function useUpdateGrantMutation(kbId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ grantId, payload }: { grantId: number; payload: ServiceGrantUpdateRequest }) => grantsApi.grants.update(kbId, grantId, payload),
    onSuccess: () => client.invalidateQueries({ queryKey: grantKeys.grants(kbId) }),
  });
}
