import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockFetch } from "../../test/mockFetch";
import { loginAs, renderRoutes } from "../../test/render";
import { OpsPage } from "./OpsPage";

describe("ops page", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders queue metrics, store health, workers and failures with task links", async () => {
    loginAs();
    mockFetch([
      ({ path }) => (path === "/ops/overview" ? { knowledge_bases: 2, documents: 11, chunks: 40, tasks_total: 9, tasks_pending: 1, tasks_running: 0, tasks_claimed_stale: 0, avg_task_wait_ms: 1200, avg_task_run_ms: 3400, long_term_memories: 0, short_term_memories: 0, memory_ingestions: 0, retrieval_logs: 5, source_assets_missing: 0, source_assets_stale: 1, uploads: 3 } : undefined),
      ({ path }) => (path === "/ops/stores/health" ? { database: "ok", vector_store_mode: "db", vector_store_status: { backend: "db", status: "ok" }, model_provider_mode: "mock", model_provider_status: "mock-or-not-configured", object_storage_endpoint: "http://127.0.0.1:6066", object_storage_region: "us-east-1" } : undefined),
      ({ path }) => (path === "/ops/workers" ? [{ worker_name: "knowledge-worker-1", status: "idle", last_seen_at: new Date().toISOString(), last_processed_at: null, processed_count: 7, last_error: null, active_tasks_count: 0 }] : undefined),
      ({ path }) => (path === "/ops/tasks/failures" ? [{ id: 42, kb_id: 7, task_type: "import", status: "failed", trace_id: "tr-1", source_paths: ["/apps/x/a.md"], error_message: "parse error", stats_json: {}, finished_at: "2026-10-01T00:00:00", created_at: "2026-10-01T00:00:00" }] : undefined),
    ]);
    renderRoutes([{ path: "/ops", element: <OpsPage /> }], "/ops");

    expect(await screen.findByText("排队任务")).toBeInTheDocument();
    expect(screen.getByText("1.2 s / 3.4 s")).toBeInTheDocument();
    expect(screen.getByText("未配置（mock）")).toBeInTheDocument();
    expect(await screen.findByText("knowledge-worker-1")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "42" })).toHaveAttribute("href", "/kbs/7/assets?task=42");
    expect(screen.getByText("parse error")).toBeInTheDocument();
  });
});
