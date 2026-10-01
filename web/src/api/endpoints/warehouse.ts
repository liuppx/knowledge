import { request } from "../client";
import type { Schema } from "../types";

export type WarehouseStatus = Schema<"WarehouseStatusResponse">;
export type Credential = Schema<"WarehouseCredentialSummary">;
export type CredentialCreateRequest = Schema<"WarehouseCredentialCreateRequest">;
export type CredentialReveal = Schema<"WarehouseCredentialRevealResponse">;
export type WriteCredentialResponse = Schema<"WarehouseWriteCredentialResponse">;
export type BrowseResponse = Schema<"WarehouseBrowseResponse">;
export type WarehouseEntry = Schema<"WarehouseEntry">;
export type WarehousePreview = Schema<"WarehousePreviewResponse">;
export type UploadResponse = Schema<"UploadResponse">;
export type UploadRecord = Schema<"UploadRecordRead">;
export type BootstrapChallenge = Schema<"WarehouseBootstrapChallengeResponse">;
export type BootstrapInitializeRequest = Schema<"WarehouseBootstrapInitializeRequest">;
export type BootstrapInitializeResponse = Schema<"WarehouseBootstrapInitializeResponse">;
export type Binding = Schema<"SourceBindingResponse">;
export type BindingCreateRequest = Schema<"SourceBindingCreateRequest">;
export type BindingUpdateRequest = Schema<"SourceBindingUpdateRequest">;

/** Which credential a browse/preview call uses: a read credential id, or the write credential. */
export type BrowseAccess = { credentialId?: number | null; useWriteCredential?: boolean };

function accessQuery(path: string, access: BrowseAccess) {
  return { path, credential_id: access.credentialId ?? undefined, use_write_credential: access.useWriteCredential ? true : undefined };
}

export const warehouseApi = {
  status: () => request<WarehouseStatus>("/warehouse/status"),
  readCredentials: {
    list: () => request<Credential[]>("/warehouse/credentials/read"),
    create: (payload: CredentialCreateRequest) => request<Credential>("/warehouse/credentials/read", { method: "POST", json: payload }),
    reveal: (credentialId: number) => request<CredentialReveal>(`/warehouse/credentials/read/${credentialId}/secret`),
    remove: (credentialId: number) => request<unknown>(`/warehouse/credentials/read/${credentialId}`, { method: "DELETE" }),
  },
  writeCredential: {
    get: () => request<WriteCredentialResponse>("/warehouse/credentials/write"),
    save: (payload: CredentialCreateRequest) => request<Credential>("/warehouse/credentials/write", { method: "POST", json: payload }),
    reveal: () => request<CredentialReveal>("/warehouse/credentials/write/secret"),
    remove: () => request<unknown>("/warehouse/credentials/write", { method: "DELETE" }),
  },
  browse: (path: string, access: BrowseAccess) => request<BrowseResponse>("/warehouse/browse", { query: accessQuery(path, access) }),
  preview: (path: string, access: BrowseAccess) => request<WarehousePreview>("/warehouse/preview", { query: accessQuery(path, access) }),
  upload: (file: File, targetDir: string) => {
    const body = new FormData();
    body.append("file", file);
    body.append("target_dir", targetDir);
    return request<UploadResponse>("/warehouse/upload", { method: "POST", body });
  },
  uploads: () => request<UploadRecord[]>("/warehouse/uploads"),
  bootstrapChallenge: () => request<BootstrapChallenge>("/warehouse/bootstrap/challenge", { method: "POST" }),
  bootstrapInitialize: (payload: BootstrapInitializeRequest) =>
    request<BootstrapInitializeResponse>("/warehouse/bootstrap/initialize", { method: "POST", json: payload }),
  bindings: {
    list: (kbId: number) => request<Binding[]>(`/kbs/${kbId}/bindings`),
    create: (kbId: number, payload: BindingCreateRequest) => request<Binding>(`/kbs/${kbId}/bindings`, { method: "POST", json: payload }),
    update: (kbId: number, bindingId: number, payload: BindingUpdateRequest) =>
      request<Binding>(`/kbs/${kbId}/bindings/${bindingId}`, { method: "PATCH", json: payload }),
    remove: (kbId: number, bindingId: number) => request<unknown>(`/kbs/${kbId}/bindings/${bindingId}`, { method: "DELETE" }),
  },
};
