import { useQuery } from "@tanstack/react-query";

import { request } from "../client";
import type { Schema } from "../types";

export type OpsOverview = Schema<"OpsOverviewResponse">;
export type StoresHealth = Schema<"StoresHealthResponse">;
export type WorkerStatus = Schema<"WorkerStatusRead">;
export type TaskFailure = Schema<"TaskFailureRead">;

export const opsApi = {
  overview: () => request<OpsOverview>("/ops/overview"),
  storesHealth: () => request<StoresHealth>("/ops/stores/health"),
  workers: () => request<WorkerStatus[]>("/ops/workers"),
  failures: (traceId?: string, limit = 20) => request<TaskFailure[]>("/ops/tasks/failures", { query: { trace_id: traceId || undefined, limit } }),
};

const OPS_POLL_MS = 10_000;

export function useOpsOverviewQuery() {
  return useQuery({ queryKey: ["ops", "overview"], queryFn: opsApi.overview, refetchInterval: OPS_POLL_MS });
}
export function useStoresHealthQuery() {
  return useQuery({ queryKey: ["ops", "stores"], queryFn: opsApi.storesHealth, refetchInterval: 30_000 });
}
export function useWorkersQuery() {
  return useQuery({ queryKey: ["ops", "workers"], queryFn: opsApi.workers, refetchInterval: OPS_POLL_MS });
}
export function useFailuresQuery(traceId: string) {
  return useQuery({ queryKey: ["ops", "failures", traceId], queryFn: () => opsApi.failures(traceId) });
}
