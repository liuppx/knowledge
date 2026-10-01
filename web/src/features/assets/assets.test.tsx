import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { json, mockFetch, type Handler } from "../../test/mockFetch";
import { loginAs, renderRoutes } from "../../test/render";
import { AssetsPage } from "./AssetsPage";

const routes = [{ path: "/kbs/:kbId/assets", element: <AssetsPage /> }];

const TASK = (id: number, status: string, extra: Record<string, unknown> = {}) => ({
  id,
  owner_wallet_address: "0x",
  kb_id: 7,
  task_type: "import",
  status,
  source_paths: ["/apps/x/uploads/a.md"],
  stats_json: {},
  error_message: status === "failed" ? "boom" : "",
  created_at: "2026-01-02T00:00:00",
  started_at: null,
  finished_at: null,
  queue_state: null,
  queue_position: status === "pending" ? 2 : null,
  current_running_task_id: null,
  current_running_task_type: null,
  cancelable: status === "pending" || status === "running",
  claimed_by: null,
  heartbeat_at: null,
  last_stage: status === "running" ? "parsing" : null,
  wait_duration_ms: null,
  run_duration_ms: null,
  ...extra,
});

const base: Handler[] = [
  ({ path }) => (path === "/warehouse/status" ? { wallet_address: "0x", credentials_ready: true, read_credentials_count: 1, current_app_root: "/apps/x", current_app_upload_dir: "/apps/x/uploads" } : undefined),
  ({ path, method }) => (path === "/warehouse/credentials/read" && method === "GET" ? [{ id: 3, credential_kind: "read", key_id: "AKREAD", key_secret_masked: "***", root_path: "/apps/x", status: "active", created_at: "", updated_at: "" }] : undefined),
  ({ path, method }) => (path === "/warehouse/credentials/write" && method === "GET" ? { configured: false, credential: null } : undefined),
];

describe("assets workbench", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists tasks with queue descriptions, polls while active and retries failed ones", async () => {
    loginAs();
    const calls = mockFetch([
      ...base,
      ({ path, method }) => (path === "/tasks" && method === "GET" ? [TASK(1, "pending"), TASK(2, "failed"), { ...TASK(3, "succeeded"), kb_id: 9 }] : undefined),
      ({ path, method }) => (path === "/tasks/2/retry" && method === "POST" ? TASK(2, "pending") : undefined),
    ]);
    renderRoutes(routes, "/kbs/7/assets?tab=tasks");
    const user = userEvent.setup();

    expect(await screen.findByText("排队中 · 第 2 位")).toBeInTheDocument();
    expect(screen.getByText("有任务进行中，每 3 秒刷新")).toBeInTheDocument();
    // Task 3 belongs to another KB and must not leak into this one.
    expect(screen.queryByText("3", { selector: "td" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "重试任务 2" }));
    await waitFor(() => expect(calls.some((call) => call.method === "POST" && call.url === "/tasks/2/retry")).toBe(true));
  });

  it("creates an import task from a source path with the chosen credential", async () => {
    loginAs();
    const created: unknown[] = [];
    const calls = mockFetch([
      ...base,
      ({ path, method }) => (path === "/tasks" && method === "GET" ? created : undefined),
      ({ path, method, body }) => {
        if (path !== "/kbs/7/tasks/import" || method !== "POST") return undefined;
        const task = TASK(11, "pending", { source_paths: (body as { source_paths: string[] }).source_paths });
        created.push(task);
        return task;
      },
      ({ path }) => (path === "/tasks/11/items" ? [] : undefined),
    ]);
    const { router } = renderRoutes(routes, "/kbs/7/assets?tab=tasks");
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("源路径"), "/apps/x/uploads/demo.md");
    await user.selectOptions(screen.getByLabelText("凭证"), "3");
    await user.click(screen.getByRole("button", { name: "导入" }));

    await waitFor(() => expect(calls.find((call) => call.url === "/kbs/7/tasks/import")?.body).toEqual({ source_paths: ["/apps/x/uploads/demo.md"], credential_id: 3 }));
    // The new task opens in the drawer via the ?task= deep link.
    await waitFor(() => expect(router.state.location.search).toContain("task=11"));
    expect(await screen.findByRole("dialog")).toHaveTextContent("任务 #11");
  });

  it("toggles a binding and unbinds after confirmation", async () => {
    loginAs();
    const calls = mockFetch([
      ...base,
      ({ path, method }) =>
        path === "/kbs/7/bindings" && method === "GET"
          ? [{ id: 5, kb_id: 7, source_type: "warehouse", source_path: "/apps/x/docs", scope_type: "directory", credential_id: 3, credential_key_id: "AKREAD", enabled: true, sync_status: "synced", document_count: 2, chunk_count: 9, active_task_count: 0 }]
          : undefined,
      ({ path, method, body }) => (path === "/kbs/7/bindings/5" && method === "PATCH" ? { id: 5, kb_id: 7, source_type: "warehouse", source_path: "/apps/x/docs", scope_type: "directory", enabled: (body as { enabled: boolean }).enabled, sync_status: "synced", document_count: 2, chunk_count: 9, active_task_count: 0 } : undefined),
      ({ path, method }) => (path === "/kbs/7/bindings/5" && method === "DELETE" ? { ok: true } : undefined),
      ({ path, method }) => (path === "/tasks" && method === "GET" ? [] : undefined),
    ]);
    renderRoutes(routes, "/kbs/7/assets");
    const user = userEvent.setup();

    await user.click(await screen.findByLabelText("启用 /apps/x/docs"));
    await waitFor(() => expect(calls.find((call) => call.method === "PATCH")?.body).toEqual({ enabled: false }));

    await user.click(screen.getByRole("button", { name: "解绑 /apps/x/docs" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "解绑" }));
    await waitFor(() => expect(calls.some((call) => call.method === "DELETE" && call.url === "/kbs/7/bindings/5")).toBe(true));
  });

  it("shows documents with processing status and deletes an index after confirmation", async () => {
    loginAs();
    const calls = mockFetch([
      ...base,
      ({ path, method }) =>
        path === "/kbs/7/documents" && method === "GET"
          ? [{ id: 21, source_path: "/apps/x/uploads/a.md", source_file_name: "a.md", file_type: "markdown", source_kind: "warehouse", parse_status: "parsed", chunk_count: 4, last_indexed_at: "2026-01-02T00:00:00" }]
          : undefined,
      ({ path, method }) => (path === "/kbs/7/documents/21" && method === "DELETE" ? json({ ok: true }) : undefined),
      ({ path, method }) => (path === "/tasks" && method === "GET" ? [] : undefined),
    ]);
    renderRoutes(routes, "/kbs/7/assets?tab=documents");
    const user = userEvent.setup();

    expect(await screen.findByText("a.md")).toBeInTheDocument();
    expect(screen.getByText("4", { selector: "td" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "删除 a.md" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "删除索引" }));
    await waitFor(() => expect(calls.some((call) => call.method === "DELETE" && call.url === "/kbs/7/documents/21")).toBe(true));
  });
});
