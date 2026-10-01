import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { json, mockFetch, type Handler } from "../../test/mockFetch";
import { loginAs, renderRoutes } from "../../test/render";
import { ReleasePage } from "./ReleasePage";
import { diffReleases } from "./diff";

const routes = [{ path: "/kbs/:kbId/release", element: <ReleasePage /> }];

const release = (id: number, version: string, status = "superseded") => ({ id, kb_id: 7, version, status, release_note: "", published_at: "2026-10-0" + id + "T00:00:00", created_by: "0xabcdef1234567890", supersedes_release_id: id > 1 ? id - 1 : null, created_at: "", updated_at: "" });
const item = (id: number, knowledgeItemId: number, revisionId: number, hash = "h") => ({ id, release_id: 0, knowledge_item_id: knowledgeItemId, knowledge_item_revision_id: revisionId, item_version_hash: hash, content_health_status: "healthy" });
const PRINCIPAL = { id: 2, owner_wallet_address: "0x", service_id: "chat.yeying.pub", display_name: "Chat", identity_type: "api_key", credential_fingerprint: "fp", public_key_jwk: {}, principal_status: "active", created_at: "", updated_at: "" };

const base: Handler[] = [
  ({ path, method }) => (path === "/kbs/7/releases" && method === "GET" ? [release(1, "2026.09.01"), release(2, "2026.10.01", "published")] : undefined),
  ({ path }) => (path === "/kbs/7/releases/current" ? { release: release(2, "2026.10.01", "published"), items: [item(1, 5, 9), item(2, 6, 11, "h2")] } : undefined),
  ({ path }) => (path === "/kbs/7/releases/1" ? { release: release(1, "2026.09.01"), items: [item(1, 5, 9), item(3, 8, 20)] } : undefined),
  ({ path }) => (path === "/kbs/7/releases/2" ? { release: release(2, "2026.10.01", "published"), items: [item(1, 5, 9), item(2, 6, 11, "h2")] } : undefined),
  ({ path, method }) => (path === "/service-principals" && method === "GET" ? [PRINCIPAL] : undefined),
  ({ path, method }) => (path === "/kbs/7/grants" && method === "GET" ? [] : undefined),
  ({ path }) => (path === "/kbs/7/items" ? [] : undefined),
];

describe("release & grants workbench", () => {
  afterEach(() => vi.restoreAllMocks());

  it("publishes a new version", async () => {
    loginAs();
    const calls = mockFetch([...base, ({ path, method, body }) => (path === "/kbs/7/releases" && method === "POST" ? { release: release(3, (body as { version: string }).version, "published"), items: [item(1, 5, 9)] } : undefined)]);
    renderRoutes(routes, "/kbs/7/release");
    const user = userEvent.setup();

    expect(await screen.findByText("2026.10.01")).toBeInTheDocument();
    expect(screen.getByText("当前")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "发布新版本" }));
    const form = screen.getByRole("form", { name: "发布表单" });
    const version = within(form).getByLabelText("版本号");
    await user.clear(version);
    await user.type(version, "2026.10.02");
    await user.type(within(form).getByLabelText("发布说明"), "新增凭证说明");
    await user.click(within(form).getByRole("button", { name: "发布" }));

    await waitFor(() => expect(calls.find((call) => call.method === "POST" && call.url === "/kbs/7/releases")?.body).toEqual({ version: "2026.10.02", release_note: "新增凭证说明" }));
    expect(await screen.findByText(/已发布 2026.10.02/)).toBeInTheDocument();
  });

  it("diffs two releases by knowledge item", async () => {
    loginAs();
    mockFetch(base);
    renderRoutes(routes, "/kbs/7/release");
    const user = userEvent.setup();

    await screen.findByText("2026.10.01");
    await user.selectOptions(screen.getByLabelText("对比 2026.10.01"), "1");
    const list = await screen.findByRole("list", { name: "版本差异" });
    expect(within(list).getByText("新增")).toBeInTheDocument(); // item 6 only in 2026.10.01
    expect(within(list).getByText("移除")).toBeInTheDocument(); // item 8 only in 2026.09.01

    const diff = diffReleases([item(1, 5, 9), item(3, 8, 20)], [item(1, 5, 10), item(2, 6, 11)]);
    expect(diff.added.map((entry) => entry.knowledge_item_id)).toEqual([6]);
    expect(diff.removed.map((entry) => entry.knowledge_item_id)).toEqual([8]);
    expect(diff.changed.map((entry) => entry.after.knowledge_item_id)).toEqual([5]);
    expect(diff.unchanged).toBe(0);
  });

  it("creates a service principal, shows the key once, and grants it a pinned release", async () => {
    loginAs();
    const calls = mockFetch([
      ...base,
      ({ path, method, body }) => (path === "/service-principals" && method === "POST" ? { principal: { ...PRINCIPAL, id: 3, service_id: (body as { service_id: string }).service_id, display_name: "Agent" }, api_key: "sk_once_only" } : undefined),
      ({ path, method }) => (path === "/kbs/7/grants" && method === "POST" ? json({ id: 9, owner_wallet_address: "0x", kb_id: 7, service_principal_id: 2, grant_status: "active", release_selection_mode: "pinned_release", pinned_release_id: 2, default_result_mode: "referenced", revoked_by: "", created_at: "", updated_at: "" }) : undefined),
    ]);
    renderRoutes(routes, "/kbs/7/release?tab=grants");
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("service_id"), "agent.yeying.pub");
    await user.type(screen.getByLabelText("显示名称"), "Agent");
    await user.click(screen.getByRole("button", { name: "创建并签发 Key" }));
    expect(await screen.findByText("sk_once_only")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "新增授权" }));
    const form = screen.getByRole("form", { name: "授权表单" });
    await user.selectOptions(within(form).getByLabelText("发布选择"), "pinned_release");
    await user.selectOptions(within(form).getByLabelText("固定版本"), "2");
    await user.selectOptions(within(form).getByLabelText("默认结果视图"), "referenced");
    await user.click(within(form).getByRole("button", { name: "创建授权" }));

    await waitFor(() => expect(calls.find((call) => call.method === "POST" && call.url === "/kbs/7/grants")?.body).toEqual({ service_principal_id: 2, release_selection_mode: "pinned_release", pinned_release_id: 2, default_result_mode: "referenced", expires_at: null }));
  });
});
