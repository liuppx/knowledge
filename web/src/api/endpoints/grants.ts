import { request } from "../client";
import type { Schema } from "../types";

export type ServicePrincipal = Schema<"ServicePrincipalRead">;
export type ServicePrincipalCreateRequest = Schema<"ServicePrincipalCreateRequest">;
export type ServicePrincipalCreateResponse = Schema<"ServicePrincipalCreateResponse">;
export type ServicePrincipalUpdateRequest = Schema<"ServicePrincipalUpdateRequest">;
export type ServiceGrant = Schema<"ServiceGrantRead">;
export type ServiceGrantCreateRequest = Schema<"ServiceGrantCreateRequest">;
export type ServiceGrantUpdateRequest = Schema<"ServiceGrantUpdateRequest">;

export const RELEASE_SELECTION_MODES = [
  { value: "latest_published", label: "最新发布", description: "随每次发布自动切换" },
  { value: "pinned_release", label: "固定版本", description: "锁定到指定 release，需要手动升级" },
] as const;

export const grantsApi = {
  principals: {
    list: () => request<ServicePrincipal[]>("/service-principals"),
    create: (payload: ServicePrincipalCreateRequest) => request<ServicePrincipalCreateResponse>("/service-principals", { method: "POST", json: payload }),
    update: (principalId: number, payload: ServicePrincipalUpdateRequest) => request<ServicePrincipal>(`/service-principals/${principalId}`, { method: "PATCH", json: payload }),
  },
  grants: {
    list: (kbId: number) => request<ServiceGrant[]>(`/kbs/${kbId}/grants`),
    create: (kbId: number, payload: ServiceGrantCreateRequest) => request<ServiceGrant>(`/kbs/${kbId}/grants`, { method: "POST", json: payload }),
    update: (kbId: number, grantId: number, payload: ServiceGrantUpdateRequest) => request<ServiceGrant>(`/kbs/${kbId}/grants/${grantId}`, { method: "PATCH", json: payload }),
  },
};
