import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { KB, WORKBENCH, json, mockFetch } from "../test/mockFetch";
import { loginAs, renderRoutes } from "../test/render";
import { rememberKbId } from "./lastKb";
import { routes } from "./router";

function mockApi() {
  return mockFetch([
    ({ method, path }) => (method === "GET" && path === "/kbs" ? [KB(7, "Handbook"), KB(9, "Second")] : undefined),
    ({ path }) => (path === "/kbs/7" ? KB(7, "Handbook") : undefined),
    ({ path }) => (path === "/kbs/7/workbench" ? WORKBENCH(7, { kb_name: "Handbook" }) : undefined),
    ({ path }) => (path === "/kbs/7/releases/current" ? json({ detail: "none" }, 404) : undefined),
    ({ method }) => (method === "GET" ? [] : undefined),
  ]);
}

describe("app routing", () => {
  afterEach(() => vi.restoreAllMocks());

  it("redirects anonymous users to /login", async () => {
    mockApi();
    const { router } = renderRoutes(routes, "/kbs/7/search");
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
  });

  it("marks the active workbench section and scopes nav links to the KB in the URL", async () => {
    loginAs();
    mockApi();
    renderRoutes(routes, "/kbs/7/search");

    const active = await screen.findByRole("link", { name: /检索台/ });
    expect(active).toHaveClass("active");
    expect(screen.getByRole("link", { name: /资产与导入/ })).toHaveAttribute("href", "/kbs/7/assets");
    await waitFor(() => expect(screen.getByLabelText("选择知识库")).toHaveValue("7"));
  });

  it("sends / to the last used KB overview", async () => {
    loginAs();
    rememberKbId(7);
    mockApi();
    const { router } = renderRoutes(routes, "/");

    await waitFor(() => expect(router.state.location.pathname).toBe("/kbs/7/overview"));
    expect(await screen.findByRole("heading", { level: 1, name: "Handbook" })).toBeInTheDocument();
  });

  it("falls back to the KB list without a remembered KB", async () => {
    loginAs();
    mockApi();
    const { router } = renderRoutes(routes, "/");
    await waitFor(() => expect(router.state.location.pathname).toBe("/kbs"));
  });
});
