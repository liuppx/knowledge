import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mockFetch, type Handler } from "../../../test/mockFetch";
import { loginAs, renderRoutes } from "../../../test/render";
import { ProductionPage } from "../ProductionPage";

// 夜莺钱包:知行图接口(zhixing_requestAccounts / zhixing_signKnowledgeOp)。
// 每个测试设置 wallet.impl;用普通对象而不是 vi.fn,避免 restoreAllMocks 把它还原成空实现
const PUBKEY = "ab".repeat(32);
type WalletArgs = { method: string; params?: unknown[] };
const wallet: { impl: (args: WalletArgs) => Promise<unknown>; calls: WalletArgs[] } = {
  impl: async () => { throw new Error("wallet impl not set"); },
  calls: [],
};
vi.mock("@yeying-community/web3-bs", () => ({
  getProvider: async () => ({ request: (args: WalletArgs) => { wallet.calls.push(args); return wallet.impl(args); } }),
  loginWithWalletIdentity: async () => undefined,
  requestAccounts: async () => [],
}));

const routes = [{ path: "/kbs/:kbId/production", element: <ProductionPage /> }];
const ITEM = { id: 5, kb_id: 7, item_type: "fact", origin_type: "manual", lifecycle_status: "confirmed", current_revision_id: 9, is_hotfix: false, created_at: "", updated_at: "2026-01-03T00:00:00", title: "渐进超负荷", statement: "身体只会对超过它已经适应的负荷产生适应。", revision_no: 1, review_status: "accepted", visibility_status: "active", evidence_count: 0 };
const REVISION = { id: 9, knowledge_item_id: 5, revision_no: 1, title: "渐进超负荷", statement: "身体只会对超过它已经适应的负荷产生适应。", structured_payload_json: {}, item_contract_version: "v1", review_status: "accepted", visibility_status: "active", created_by: "0xabc", reviewed_by: "", provenance_type: "manual", provenance_json: {}, source_note: "", applicability_scope_json: {}, is_workspace_head: true, created_at: "2026-01-03T00:00:00", updated_at: "2026-01-03T00:00:00", evidence_links: [] };
const PUBLICATION = { id: 31, revision_id: 9, network: "testnet", status: "prepared", op_type: "create", chain_unit: null, chain_version: 1, body_sha256: "cd".repeat(32), body_url: "https://blockchain.yeying.pub/bodies/x", op_hash: "", actor: 2, actor_pubkey: PUBKEY, error: "", created_at: "", updated_at: "" };
const INTENT = { actor: "2", nonce: "4", action: { type: "create", layer: "foundation", domain: 2, bodies: [{ lang: "zh", hash: "cd".repeat(32) }], source: { type: "human" }, cites: [] } };
const STATUS = (overrides: Record<string, unknown> = {}) => ({
  enabled: true, network: "testnet", domains: [{ id: 1, name_zh: "大模型应用开发", name_en: "LLM" }, { id: 2, name_zh: "运动健身", name_en: "Fitness" }],
  domain: 2, layer: "foundation", chain_unit: null, chain_version: null, unit_url: null, current_revision_published: false,
  pending: null, relations: [], publications: [], ...overrides,
});

function base(status = STATUS()): Handler[] {
  return [
    ({ path }) => (path === "/kbs/7/sources" ? [] : undefined),
    ({ path }) => (path === "/kbs/7/assets" ? [] : undefined),
    ({ path, method }) => (path === "/kbs/7/evidence" && method === "GET" ? [] : undefined),
    ({ path, method }) => (path === "/kbs/7/candidates" && method === "GET" ? [] : undefined),
    ({ path, method }) => (path === "/kbs/7/items" && method === "GET" ? [ITEM] : undefined),
    ({ path }) => (path === "/kbs/7/items/5" ? { item: ITEM, current_revision: REVISION, revisions: [REVISION] } : undefined),
    ({ path, method }) => (path === "/kbs/7/items/5/kdg" && method === "GET" ? status : undefined),
  ];
}

async function openItem() {
  renderRoutes(routes, "/kbs/7/production?tab=items");
  const user = userEvent.setup();
  await user.click(await screen.findByText("渐进超负荷"));
  const dialog = await screen.findByRole("dialog");
  await within(dialog).findByRole("region", { name: "知行图" });
  return { user, dialog };
}

describe("上链到知行图", () => {
  beforeEach(() => { wallet.calls = []; });
  afterEach(() => vi.restoreAllMocks());

  it("钱包确认连接与签名后提交,并显示链上单元", async () => {
    loginAs();
    wallet.impl = async ({ method }: WalletArgs) => {
      if (method === "zhixing_requestAccounts") return [PUBKEY];
      if (method === "zhixing_signKnowledgeOp") return { signed: "00".repeat(40), address: PUBKEY };
      throw new Error("unexpected " + method);
    };
    const calls = mockFetch([
      ...base(),
      ({ path, method }) => (path === "/kbs/7/items/5/kdg/prepare" && method === "POST" ? { publication: PUBLICATION, intent: INTENT, body_markdown: "# 渐进超负荷\n" } : undefined),
      ({ path, method }) => (path === "/kbs/7/items/5/kdg/publications/31/submit" && method === "POST" ? { ...PUBLICATION, status: "confirmed", chain_unit: 3, chain_version: 1 } : undefined),
    ]);
    const { user, dialog } = await openItem();

    await user.click(within(dialog).getByRole("button", { name: "上链到知行图" }));

    await waitFor(() => expect(screen.getByText(/已上链：知行图单元 #3 v1/)).toBeInTheDocument());
    // 网页递给钱包的是后端准备好的意图(谁、第几条、做什么),不是待签字节
    const sign = wallet.calls.find((a) => a.method === "zhixing_signKnowledgeOp")!;
    expect(sign.params?.[0]).toEqual({ actor: "2", nonce: "4", action: INTENT.action });
    expect(calls.find((c) => c.url === "/kbs/7/items/5/kdg/prepare")?.body).toEqual({ pubkey: PUBKEY });
    expect(calls.find((c) => c.url.endsWith("/submit"))?.body).toEqual({ signed: "00".repeat(40), address: PUBKEY });
  });

  it("在钱包里取消签名:提示取消,不提交", async () => {
    loginAs();
    wallet.impl = async ({ method }: WalletArgs) => {
      if (method === "zhixing_requestAccounts") return [PUBKEY];
      const err = Object.assign(new Error("User rejected"), { code: 4001 });
      throw err;
    };
    const calls = mockFetch([
      ...base(),
      ({ path, method }) => (path === "/kbs/7/items/5/kdg/prepare" && method === "POST" ? { publication: PUBLICATION, intent: INTENT, body_markdown: "" } : undefined),
    ]);
    const { user, dialog } = await openItem();

    await user.click(within(dialog).getByRole("button", { name: "上链到知行图" }));

    expect(await screen.findByText(/你在钱包里取消了/)).toBeInTheDocument();
    expect(calls.some((c) => c.url.endsWith("/submit"))).toBe(false);
  });

  it("钱包里没有知行图账户:给出导入指引", async () => {
    loginAs();
    wallet.impl = async () => {
      throw Object.assign(new Error("no zhixing account"), { code: 4900 });
    };
    mockFetch(base());
    const { user, dialog } = await openItem();

    await user.click(within(dialog).getByRole("button", { name: "上链到知行图" }));

    expect(await screen.findByText(/账户管理 → 导入钱包/)).toBeInTheDocument();
  });

  it("没设领域与层级时不能上链;已上链时显示单元链接", async () => {
    loginAs();
    mockFetch(base(STATUS({ domain: null, layer: null })));
    const { dialog } = await openItem();
    expect(within(dialog).getByRole("button", { name: "上链到知行图" })).toBeDisabled();
    expect(within(dialog).getByLabelText("知行图领域")).toHaveDisplayValue("请选择");
  });

  it("上链未开启时只给说明", async () => {
    loginAs();
    mockFetch(base(STATUS({ enabled: false })));
    renderRoutes(routes, "/kbs/7/production?tab=items");
    const user = userEvent.setup();
    await user.click(await screen.findByText("渐进超负荷"));
    expect(await screen.findByText(/知行图上链未开启/)).toBeInTheDocument();
  });
});
