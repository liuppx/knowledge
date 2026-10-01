import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockFetch, type Handler } from "../../test/mockFetch";
import { loginAs, renderRoutes } from "../../test/render";
import { SearchPage } from "./SearchPage";
import { collectSignals } from "./TraceView";

const routes = [{ path: "/kbs/:kbId/search", element: <SearchPage /> }];

const RELEASE = { id: 3, kb_id: 7, version: "2026.10.01", status: "published", release_note: "", published_at: "2026-10-01T00:00:00", created_by: "0x", created_at: "", updated_at: "" };
const FORMAL_HIT = { result_kind: "formal", score: 0.9123, content_health_status: "healthy", source_health_summary: "healthy", source_refs: ["/apps/x/docs/cred.md"], knowledge_item_id: 5, knowledge_item_revision_id: 9, title: "读凭证用途", statement: "读凭证用于浏览与绑定。", item_type: "fact", evidence_summaries: [{ evidence_id: 12, evidence_type: "paragraph", text_excerpt: "读凭证用于浏览 warehouse 目录", content_health_status: "healthy", source_ref: "/apps/x/docs/cred.md" }], source_health_details: [], audit_info: { ranking_factors: { mode: "formal" } } };
const EVIDENCE_HIT = { result_kind: "evidence", score: 0.5, content_health_status: "stale", source_health_summary: "stale", source_refs: [], evidence_id: 12, evidence_type: "paragraph", text: "读凭证用于浏览 warehouse 目录。", evidence_summaries: [], source_health_details: [{ source_id: 3, asset_id: 4, asset_path: "/apps/x/docs/cred.md", availability_status: "changed" }], audit_info: {} };
const empty = (mode: string) => ({ kb_id: 7, mode, result_view: "audit", availability_mode: "allow_all", release: null, grant: null, hits: [] });

const base: Handler[] = [
  ({ path }) => (path === "/kbs/7/retrieval-logs" ? [{ id: 31, owner_wallet_address: "0x", kb_id: 7, query: "读凭证", query_mode: "search_lab_compare", release_id: 3, result_summary_json: { hits: 2 }, trace_json: { formal_first: { hybrid_enabled: true, vector_signal: "active", vector_widened: 2, rerank_enabled: true, rerank_signal: "degraded:TimeoutError" } }, created_at: "2026-10-01T01:00:00" }] : undefined),
  ({ path }) => (path === "/kbs/7/retrieval-logs/31" ? { id: 31, owner_wallet_address: "0x", kb_id: 7, query: "读凭证", query_mode: "search_lab_compare", release_id: 3, result_summary_json: { hits: 2 }, trace_json: { vector_signal: "active", vector_widened: 2, rerank_signal: "degraded:TimeoutError", rerank_count: 0 }, created_at: "2026-10-01T01:00:00" } : undefined),
  ({ path }) => (path === "/kbs/7/source-governance" ? { kb_id: 7, status_counts: { available: 3, changed: 1 }, sources: [], assets: [{ asset_id: 4, source_id: 3, asset_path: "/apps/x/docs/cred.md", availability_status: "changed", evidence_count: 2 }] } : undefined),
];

describe("search lab", () => {
  afterEach(() => vi.restoreAllMocks());

  it("runs a compare and renders the three modes with provenance links", async () => {
    loginAs();
    const calls = mockFetch([
      ...base,
      ({ path, method, body }) =>
        path === "/kbs/7/search-lab/compare" && method === "POST"
          ? { kb_id: 7, query: (body as { query: string }).query, current_release: RELEASE, retrieval_log_id: 31, formal_only: { ...empty("formal_only"), hits: [FORMAL_HIT] }, evidence_only: { ...empty("evidence_only"), hits: [EVIDENCE_HIT] }, formal_first: { ...empty("formal_first"), hits: [FORMAL_HIT, EVIDENCE_HIT] } }
          : undefined,
    ]);
    renderRoutes(routes, "/kbs/7/search");
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("查询"), "读凭证");
    await user.selectOptions(screen.getByLabelText("可用性"), "healthy_only");
    await user.click(screen.getByRole("button", { name: "运行对比" }));

    await waitFor(() => expect(calls.find((call) => call.url === "/kbs/7/search-lab/compare")?.body).toEqual({ query: "读凭证", top_k: 5, result_view: "audit", availability_mode: "healthy_only" }));
    expect(await screen.findByText("2026.10.01")).toBeInTheDocument();
    expect(screen.getByText("共 4 条命中")).toBeInTheDocument();
    const formalFirst = screen.getByRole("heading", { name: "Formal first" }).closest("section")!;
    expect(within(formalFirst).getAllByRole("link", { name: "读凭证用途" })[0]).toHaveAttribute("href", "/kbs/7/production?item=5");
    expect(within(formalFirst).getByRole("link", { name: "Evidence #12" })).toHaveAttribute("href", "/kbs/7/production?evidence=12");
    expect(within(formalFirst).getByText("已变更")).toBeInTheDocument();
  });

  it("explains next steps when nothing is hit and the KB is unpublished", async () => {
    loginAs();
    mockFetch([...base, ({ path, method }) => (path === "/kbs/7/search-lab/compare" && method === "POST" ? { kb_id: 7, query: "x", current_release: null, retrieval_log_id: null, formal_only: empty("formal_only"), evidence_only: empty("evidence_only"), formal_first: empty("formal_first") } : undefined)]);
    renderRoutes(routes, "/kbs/7/search");
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("查询"), "x");
    await user.click(screen.getByRole("button", { name: "运行对比" }));

    expect(await screen.findByText("没有命中")).toBeInTheDocument();
    expect(screen.getByText(/还没有发布版本/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "去发布" })).toHaveAttribute("href", "/kbs/7/release");
  });

  it("shows retrieval logs with hybrid/rerank signals and source health", async () => {
    loginAs();
    mockFetch(base);
    renderRoutes(routes, "/kbs/7/search");
    const user = userEvent.setup();

    expect(await screen.findByText("降级")).toBeInTheDocument(); // worst signal of the log row
    expect(screen.getByText("/apps/x/docs/cred.md", { selector: ".mono" })).toBeInTheDocument();
    await user.click(screen.getByText("读凭证", { selector: ".ellipsis" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("向量补召 2 条");
    expect(dialog).toHaveTextContent("降级：TimeoutError");
  });

  it("collects signals from flat and nested traces", () => {
    expect(collectSignals({ vector_signal: "active", rerank_signal: "mock_skipped" }).map((signal) => signal.value)).toEqual(["active", "mock_skipped"]);
    expect(collectSignals({ formal: { hybrid_enabled: false }, evidence: { vector_signal: "active_no_index" } }).map((signal) => `${signal.label}=${signal.value}`)).toEqual(["formal · 混合检索=disabled", "evidence · 混合检索=active_no_index"]);
    expect(collectSignals(null)).toEqual([]);
  });
});
