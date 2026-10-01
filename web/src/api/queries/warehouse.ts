import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { warehouseApi, type BindingCreateRequest, type BindingUpdateRequest, type BrowseAccess, type CredentialCreateRequest } from "../endpoints/warehouse";
import { kbKeys } from "./kbs";

export const warehouseKeys = {
  status: ["warehouse", "status"] as const,
  readCredentials: ["warehouse", "credentials", "read"] as const,
  writeCredential: ["warehouse", "credentials", "write"] as const,
  uploads: ["warehouse", "uploads"] as const,
  browse: (path: string, access: BrowseAccess) => ["warehouse", "browse", path, access.credentialId ?? null, Boolean(access.useWriteCredential)] as const,
  preview: (path: string, access: BrowseAccess) => ["warehouse", "preview", path, access.credentialId ?? null, Boolean(access.useWriteCredential)] as const,
  bindings: (kbId: number) => ["kbs", kbId, "bindings"] as const,
};

export function useWarehouseStatusQuery() {
  return useQuery({ queryKey: warehouseKeys.status, queryFn: warehouseApi.status });
}

export function useReadCredentialsQuery() {
  return useQuery({ queryKey: warehouseKeys.readCredentials, queryFn: warehouseApi.readCredentials.list });
}

export function useWriteCredentialQuery() {
  return useQuery({ queryKey: warehouseKeys.writeCredential, queryFn: warehouseApi.writeCredential.get });
}

export function useUploadsQuery() {
  return useQuery({ queryKey: warehouseKeys.uploads, queryFn: warehouseApi.uploads });
}

export function useBrowseQuery(path: string | null, access: BrowseAccess) {
  const enabled = path !== null && (Boolean(access.credentialId) || Boolean(access.useWriteCredential));
  return useQuery({ queryKey: warehouseKeys.browse(path ?? "", access), queryFn: () => warehouseApi.browse(path as string, access), enabled });
}

export function usePreviewQuery(path: string | null, access: BrowseAccess) {
  const enabled = path !== null && (Boolean(access.credentialId) || Boolean(access.useWriteCredential));
  return useQuery({ queryKey: warehouseKeys.preview(path ?? "", access), queryFn: () => warehouseApi.preview(path as string, access), enabled });
}

/** Any credential change can flip warehouse readiness; refresh everything that reads it. */
function useInvalidateCredentials() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: warehouseKeys.status });
    void client.invalidateQueries({ queryKey: warehouseKeys.readCredentials });
    void client.invalidateQueries({ queryKey: warehouseKeys.writeCredential });
    void client.invalidateQueries({ queryKey: ["warehouse", "browse"] });
  };
}

export function useCreateReadCredentialMutation() {
  const invalidate = useInvalidateCredentials();
  return useMutation({ mutationFn: (payload: CredentialCreateRequest) => warehouseApi.readCredentials.create(payload), onSuccess: invalidate });
}

export function useDeleteReadCredentialMutation() {
  const invalidate = useInvalidateCredentials();
  return useMutation({ mutationFn: (credentialId: number) => warehouseApi.readCredentials.remove(credentialId), onSuccess: invalidate });
}

export function useSaveWriteCredentialMutation() {
  const invalidate = useInvalidateCredentials();
  return useMutation({ mutationFn: (payload: CredentialCreateRequest) => warehouseApi.writeCredential.save(payload), onSuccess: invalidate });
}

export function useDeleteWriteCredentialMutation() {
  const invalidate = useInvalidateCredentials();
  return useMutation({ mutationFn: () => warehouseApi.writeCredential.remove(), onSuccess: invalidate });
}

export function useUploadMutation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ file, targetDir }: { file: File; targetDir: string }) => warehouseApi.upload(file, targetDir),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: warehouseKeys.uploads });
      void client.invalidateQueries({ queryKey: ["warehouse", "browse"] });
    },
  });
}

export function useBindingsQuery(kbId: number) {
  return useQuery({ queryKey: warehouseKeys.bindings(kbId), queryFn: () => warehouseApi.bindings.list(kbId) });
}

function useInvalidateBindings(kbId: number) {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: warehouseKeys.bindings(kbId) });
    void client.invalidateQueries({ queryKey: kbKeys.workbench(kbId) });
    void client.invalidateQueries({ queryKey: kbKeys.stats(kbId) });
  };
}

export function useCreateBindingMutation(kbId: number) {
  const invalidate = useInvalidateBindings(kbId);
  return useMutation({ mutationFn: (payload: BindingCreateRequest) => warehouseApi.bindings.create(kbId, payload), onSuccess: invalidate });
}

export function useUpdateBindingMutation(kbId: number) {
  const invalidate = useInvalidateBindings(kbId);
  return useMutation({
    mutationFn: ({ bindingId, payload }: { bindingId: number; payload: BindingUpdateRequest }) => warehouseApi.bindings.update(kbId, bindingId, payload),
    onSuccess: invalidate,
  });
}

export function useDeleteBindingMutation(kbId: number) {
  const invalidate = useInvalidateBindings(kbId);
  return useMutation({ mutationFn: (bindingId: number) => warehouseApi.bindings.remove(kbId, bindingId), onSuccess: invalidate });
}
