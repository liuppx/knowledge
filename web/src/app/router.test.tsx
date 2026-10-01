import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { saveSession } from "../features/auth/session";
import { ToastProvider } from "../ui";
import { rememberKbId } from "./lastKb";
import { createQueryClient } from "./queryClient";
import { routes } from "./router";

const KBS = [
  { id: 7, name: "Handbook", description: "", status: "active", retrieval_config: {}, created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00" },
  { id: 9, name: "Second", description: "", status: "active", retrieval_config: {}, created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00" },
];

function mockApi() {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    if (url === "/kbs") return json(KBS);
    if (url.endsWith("/workbench")) {
      return json({
        kb_id: 7, kb_name: "Handbook", kb_description: "", kb_status: "active",
        stats: { kb_id: 7, bindings_count: 1, documents_count: 2, chunks_count: 3, latest_task_status: "succeeded", latest_task_finished_at: null },
        binding_status_counts: { total: 1, enabled: 1, disabled: 0, indexed: 1, syncing: 0, failed: 0, pending_sync: 0 },
        bindings: [], recent_tasks: [],
      });
    }
    return json([]);
  });
}

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={createQueryClient()}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return router;
}

describe("app routing", () => {
  afterEach(() => vi.restoreAllMocks());

  it("redirects anonymous users to /login", async () => {
    mockApi();
    const router = renderAt("/kbs/7/search");
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
  });

  it("marks the active workbench section and scopes nav links to the KB in the URL", async () => {
    saveSession({ access_token: "t", refresh_token: "r", wallet_address: "0x1234567890abcdef" });
    mockApi();
    renderAt("/kbs/7/search");

    const active = await screen.findByRole("link", { name: /检索台/ });
    expect(active).toHaveClass("active");
    expect(screen.getByRole("link", { name: /资产与导入/ })).toHaveAttribute("href", "/kbs/7/assets");
    await waitFor(() => expect(screen.getByLabelText("选择知识库")).toHaveValue("7"));
  });

  it("sends / to the last used KB overview", async () => {
    saveSession({ access_token: "t", refresh_token: "r", wallet_address: "0x1234567890abcdef" });
    rememberKbId(7);
    mockApi();
    const router = renderAt("/");

    await waitFor(() => expect(router.state.location.pathname).toBe("/kbs/7/overview"));
    expect(await screen.findByRole("heading", { level: 1, name: "Handbook" })).toBeInTheDocument();
  });

  it("falls back to the KB list without a remembered KB", async () => {
    saveSession({ access_token: "t", refresh_token: "r", wallet_address: "0x1234567890abcdef" });
    mockApi();
    const router = renderAt("/");
    await waitFor(() => expect(router.state.location.pathname).toBe("/kbs"));
  });
});
