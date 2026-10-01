import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { readLastKbId, rememberKbId } from "../../app/lastKb";
import { KB, WORKBENCH, json, mockFetch } from "../../test/mockFetch";
import { loginAs, renderRoutes } from "../../test/render";
import { KbIndexPage } from "./KbIndexPage";
import { OverviewPage } from "./OverviewPage";

const routes = [
  { path: "/kbs", element: <KbIndexPage /> },
  { path: "/kbs/:kbId/overview", element: <OverviewPage /> },
];

describe("knowledge base management", () => {
  afterEach(() => vi.restoreAllMocks());

  it("edits a KB from the list and sends the retrieval config", async () => {
    loginAs();
    const calls = mockFetch([
      ({ method, path }) => (method === "GET" && path === "/kbs" ? [KB(7, "Handbook")] : undefined),
      ({ method, path, body }) => (method === "PATCH" && path === "/kbs/7" ? { ...KB(7), ...(body as object) } : undefined),
    ]);
    renderRoutes(routes, "/kbs");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "编辑 Handbook" }));
    const form = screen.getByRole("form", { name: "知识库设置" });
    const nameInput = within(form).getByDisplayValue("Handbook");
    await user.clear(nameInput);
    await user.type(nameInput, "Handbook v2");
    await user.click(within(form).getByRole("button", { name: "保存" }));

    await waitFor(() => expect(calls.some((call) => call.method === "PATCH")).toBe(true));
    const patch = calls.find((call) => call.method === "PATCH")!;
    expect(patch.body).toMatchObject({ name: "Handbook v2", retrieval_config: { chunk_size: 800, retrieval_top_k: 6 } });
    expect(await screen.findByText("知识库设置已保存")).toBeInTheDocument();
  });

  it("deletes a KB after confirmation and forgets it as the last KB", async () => {
    loginAs();
    rememberKbId(7);
    const calls = mockFetch([
      ({ method, path }) => (method === "GET" && path === "/kbs" ? [KB(7, "Handbook")] : undefined),
      ({ method, path }) => (method === "DELETE" && path === "/kbs/7" ? { ok: true } : undefined),
    ]);
    renderRoutes(routes, "/kbs");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "删除 Handbook" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("不可恢复");
    await user.click(screen.getByRole("button", { name: "删除" }));

    await waitFor(() => expect(calls.some((call) => call.method === "DELETE" && call.url === "/kbs/7")).toBe(true));
    expect(readLastKbId()).toBeNull();
  });

  it("shows the current release on the overview and guides to publish when none exists", async () => {
    loginAs();
    mockFetch([
      ({ path }) => (path === "/kbs/7" ? KB(7, "Handbook") : undefined),
      ({ path }) => (path === "/kbs/7/workbench" ? WORKBENCH(7, { kb_name: "Handbook" }) : undefined),
      ({ path }) => (path === "/kbs/7/releases/current" ? json({ detail: "no release" }, 404) : undefined),
    ]);
    renderRoutes(routes, "/kbs/7/overview");

    expect(await screen.findByRole("heading", { level: 1, name: "Handbook" })).toBeInTheDocument();
    expect(await screen.findByText("尚未发布")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "去发布" })).toHaveAttribute("href", "/kbs/7/release");
  });

  it("renders release version, bindings and recent tasks on the overview", async () => {
    loginAs();
    mockFetch([
      ({ path }) => (path === "/kbs/7" ? KB(7) : undefined),
      ({ path }) =>
        path === "/kbs/7/workbench"
          ? WORKBENCH(7, {
              bindings: [{ id: 1, kb_id: 7, source_type: "warehouse", source_path: "/apps/x/docs", scope_type: "directory", enabled: true, sync_status: "synced", document_count: 11, chunk_count: 40, active_task_count: 0 }],
              recent_tasks: [{ id: 42, task_type: "import", status: "succeeded", source_paths: ["/apps/x/docs"], created_at: "2026-01-02T00:00:00", finished_at: "2026-01-02T00:01:00" }],
            })
          : undefined,
      ({ path }) =>
        path === "/kbs/7/releases/current"
          ? { release: { id: 3, kb_id: 7, version: "2026.10.01", status: "published", release_note: "first", published_at: "2026-10-01T00:00:00", created_by: "0x", supersedes_release_id: null, created_at: "", updated_at: "" }, items: [{ id: 1, release_id: 3, knowledge_item_id: 5, knowledge_item_revision_id: 9, item_version_hash: "h", content_health_status: "healthy" }] }
          : undefined,
    ]);
    renderRoutes(routes, "/kbs/7/overview");

    expect(await screen.findByText("2026.10.01")).toBeInTheDocument();
    expect(screen.getByText("/apps/x/docs", { selector: ".mono" })).toBeInTheDocument();
    expect(screen.getByText("import")).toBeInTheDocument();
    expect(screen.getByText("成功")).toBeInTheDocument();
  });
});
