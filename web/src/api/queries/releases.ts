import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { releasesApi, type ReleaseHotfixRequest, type ReleasePublishRequest, type ReleaseRollbackRequest } from "../endpoints/releases";

export const releaseKeys = {
  all: (kbId: number) => ["kbs", kbId, "releases"] as const,
  list: (kbId: number) => ["kbs", kbId, "releases", "list"] as const,
  current: (kbId: number) => ["kbs", kbId, "releases", "current"] as const,
  detail: (kbId: number, releaseId: number) => ["kbs", kbId, "releases", releaseId] as const,
};

export function useReleasesQuery(kbId: number) {
  return useQuery({ queryKey: releaseKeys.list(kbId), queryFn: () => releasesApi.list(kbId) });
}

export function useCurrentReleaseQuery(kbId: number) {
  return useQuery({ queryKey: releaseKeys.current(kbId), queryFn: () => releasesApi.current(kbId) });
}

export function useReleaseQuery(kbId: number, releaseId: number | null) {
  return useQuery({
    queryKey: releaseKeys.detail(kbId, releaseId ?? 0),
    queryFn: () => releasesApi.get(kbId, releaseId as number),
    enabled: releaseId !== null,
  });
}

function useInvalidateReleases(kbId: number) {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: releaseKeys.all(kbId) });
}

export function usePublishReleaseMutation(kbId: number) {
  const invalidate = useInvalidateReleases(kbId);
  return useMutation({ mutationFn: (payload: ReleasePublishRequest) => releasesApi.publish(kbId, payload), onSuccess: invalidate });
}

export function useHotfixReleaseMutation(kbId: number) {
  const invalidate = useInvalidateReleases(kbId);
  return useMutation({
    mutationFn: ({ releaseId, payload }: { releaseId: number; payload: ReleaseHotfixRequest }) => releasesApi.hotfix(kbId, releaseId, payload),
    onSuccess: invalidate,
  });
}

export function useRollbackReleaseMutation(kbId: number) {
  const invalidate = useInvalidateReleases(kbId);
  return useMutation({
    mutationFn: ({ releaseId, payload }: { releaseId: number; payload: ReleaseRollbackRequest }) => releasesApi.rollback(kbId, releaseId, payload),
    onSuccess: invalidate,
  });
}
