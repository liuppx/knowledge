import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockFetch, type Handler } from "../../test/mockFetch";
import { loginAs, renderRoutes } from "../../test/render";
import { ProductionPage } from "./ProductionPage";

const routes = [{ path: "/kbs/:kbId/production", element: <ProductionPage /> }];

const SOURCE = { id: 3, kb_id: 7, source_type: "warehouse", source_path: "/apps/x/docs", scope_type: "directory", enabled: true, sync_status: "synced", missing_policy: "mark_missing", created_at: "", updated_at: "" };
const ASSET = { id: 4, kb_id: 7, source_id: 3, asset_path: "/apps/x/docs/a.md", asset_name: "a.md", asset_type: "markdown", source_version: "v1", availability_status: "available", created_at: "", updated_at: "" };
const EVIDENCE = { id: 12, kb_id: 7, asset_id: 4, evidence_type: "paragraph", text: "读凭证用于浏览 warehouse 目录。", metadata_json: {}, source_locator: { line: 3 }, vector_status: "indexed", created_at: "2026-01-02T00:00:00" };
const CANDIDATE = { id: 21, kb_id: 7, title: "读凭证用途", statement: "读凭证用于浏览与绑定。", item_type: "fact", structured_payload_json: {}, item_contract_version: "v1", origin_type: "extracted", origin_confidence: 0.82, review_status: "pending_review", created_from_job_id: "j1", provenance_json: { evidence_unit_ids: [12] }, created_at: "2026-01-02T00:00:00", updated_at: "2026-01-02T00:00:00" };
const ITEM = { id: 5, kb_id: 7, item_type: "fact", origin_type: "extracted", lifecycle_status: "confirmed", current_revision_id: 9, is_hotfix: false, created_at: "", updated_at: "2026-01-03T00:00:00", title: "读凭证用途", statement: "读凭证用于浏览与绑定。", revision_no: 1, review_status: "accepted", visibility_status: "active", evidence_count: 1 };
const REVISION = { id: 9, knowledge_item_id: 5, revision_no: 1, title: "读凭证用途", statement: "读凭证用于浏览与绑定。", structured_payload_json: {}, item_contract_version: "v1", review_status: "accepted", visibility_status: "active", created_by: "0xabc", reviewed_by: "", provenance_type: "candidate", provenance_json: {}, source_note: "", applicability_scope_json: {}, is_workspace_head: true, created_at: "2026-01-03T00:00:00", updated_at: "2026-01-03T00:00:00", evidence_links: [{ id: 1, knowledge_item_revision_id: 9, evidence_unit_id: 12, role: "support", rank: 1, summary: "来源段落" }] };

const base: Handler[] = [
  ({ path }) => (path === "/kbs/7/sources" ? [SOURCE] : undefined),
  ({ path }) => (path === "/kbs/7/assets" ? [ASSET] : undefined),
  ({ path, method }) => (path === "/kbs/7/evidence" && method === "GET" ? [EVIDENCE] : undefined),
  ({ path }) => (path === "/kbs/7/evidence/12" ? EVIDENCE : undefined),
  ({ path, method }) => (path === "/kbs/7/candidates" && method === "GET" ? [CANDIDATE] : undefined),
  ({ path, method }) => (path === "/kbs/7/items" && method === "GET" ? [ITEM] : undefined),
  ({ path }) => (path === "/kbs/7/items/5" ? { item: ITEM, current_revision: REVISION, revisions: [REVISION] } : undefined),
];

describe("production workbench", () => {
  afterEach(() => vi.restoreAllMocks());

  it("builds evidence for the selected source and reports the result", async () => {
    loginAs();
    const calls = mockFetch([...base, ({ path, method }) => (path === "/kbs/7/sources/3/build-evidence" && method === "POST" ? { kb_id: 7, source_id: 3, processed_asset_count: 1, built_evidence_count: 4, skipped_asset_count: 0, failed_asset_ids: [] } : undefined)]);
    renderRoutes(routes, "/kbs/7/production");
    const user = userEvent.setup();

    await screen.findByText("读凭证用于浏览 warehouse 目录。");
    await user.selectOptions(screen.getByLabelText("来源"), "3");
    await user.click(screen.getByRole("button", { name: "构建 Evidence" }));

    await waitFor(() => expect(calls.some((call) => call.method === "POST" && call.url === "/kbs/7/sources/3/build-evidence")).toBe(true));
    expect(await screen.findByText(/已构建 4 条 Evidence/)).toBeInTheDocument();
  });

  it("accepts a candidate with edited title and jumps to the new item", async () => {
    loginAs();
    const calls = mockFetch([...base, ({ path, method, body }) => (path === "/kbs/7/candidates/21/accept" && method === "POST" ? { item: { ...ITEM, id: 6 }, current_revision: { ...REVISION, title: (body as { title: string }).title }, revisions: [] } : undefined)]);
    const { router } = renderRoutes(routes, "/kbs/7/production?tab=candidates");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "接受 读凭证用途" }));
    const form = screen.getByRole("form", { name: "接受候选" });
    const title = within(form).getByDisplayValue("读凭证用途");
    await user.clear(title);
    await user.type(title, "读凭证与写凭证的用途");
    await user.click(within(form).getByRole("button", { name: "接受为知识项" }));

    await waitFor(() => expect(calls.find((call) => call.url === "/kbs/7/candidates/21/accept")?.body).toMatchObject({ title: "读凭证与写凭证的用途", item_type: "fact", evidence_unit_ids: [12] }));
    await waitFor(() => expect(router.state.location.search).toContain("item=6"));
  });

  it("lists items with current-revision titles and opens evidence from the detail drawer", async () => {
    loginAs();
    mockFetch(base);
    const { router } = renderRoutes(routes, "/kbs/7/production?tab=items");
    const user = userEvent.setup();

    await user.click(await screen.findByText("读凭证用途"));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Evidence 关联（1）");
    await user.click(within(dialog).getByRole("button", { name: "查看 Evidence 12" }));

    await waitFor(() => expect(router.state.location.search).toContain("evidence=12"));
    expect(await screen.findByRole("dialog")).toHaveTextContent("读凭证用于浏览 warehouse 目录。");
  });

  it("creates a manual item with parsed evidence ids", async () => {
    loginAs();
    const calls = mockFetch([...base, ({ path, method }) => (path === "/kbs/7/items/manual" && method === "POST" ? { item: { ...ITEM, id: 8, origin_type: "manual" }, current_revision: REVISION, revisions: [REVISION] } : undefined), ({ path }) => (path === "/kbs/7/items/8" ? { item: { ...ITEM, id: 8 }, current_revision: REVISION, revisions: [] } : undefined)]);
    renderRoutes(routes, "/kbs/7/production?tab=items");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "手工新建" }));
    const form = screen.getByRole("form", { name: "知识项表单" });
    await user.type(within(form).getByLabelText("标题"), "手工条目");
    await user.type(within(form).getByLabelText("陈述"), "手工录入的规则。");
    await user.selectOptions(within(form).getByLabelText("类型"), "rule");
    await user.type(within(form).getByLabelText("关联 Evidence ID（逗号分隔）"), "12, #15");
    await user.click(within(form).getByRole("button", { name: "创建" }));

    await waitFor(() => expect(calls.find((call) => call.url === "/kbs/7/items/manual")?.body).toMatchObject({ title: "手工条目", item_type: "rule", evidence_unit_ids: [12, 15], item_contract_version: "v1" }));
  });
});
