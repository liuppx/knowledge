import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockFetch, type Handler } from "../../test/mockFetch";
import { loginAs, renderRoutes } from "../../test/render";
import { WarehousePage } from "./WarehousePage";

const routes = [{ path: "/warehouse", element: <WarehousePage /> }];
const WRITE = { id: 9, credential_kind: "read_write", key_id: "AKWRITE", key_secret_masked: "***", root_path: "/apps/x", status: "active", created_at: "", updated_at: "" };

function handlers(overrides: Handler[] = []): Handler[] {
  return [
    ...overrides,
    ({ path }) => (path === "/warehouse/status" ? { wallet_address: "0x", credentials_ready: true, read_credentials_count: 0, write_credential_id: 9, write_credential_status: "active", write_root_path: "/apps/x", current_app_id: "x", current_app_root: "/apps/x", current_app_upload_dir: "/apps/x/uploads" } : undefined),
    ({ path, method }) => (path === "/warehouse/credentials/read" && method === "GET" ? [] : undefined),
    ({ path, method }) => (path === "/warehouse/credentials/write" && method === "GET" ? { configured: true, credential: WRITE } : undefined),
    ({ path }) => (path === "/warehouse/uploads" ? [] : undefined),
    ({ path }) => (path === "/warehouse/browse" ? { wallet_address: "0x", path: "/apps/x", entries: [{ path: "/apps/x/docs", name: "docs", entry_type: "directory", size: 0 }] } : undefined),
  ];
}

describe("warehouse workbench", () => {
  afterEach(() => vi.restoreAllMocks());

  it("adds a read credential", async () => {
    loginAs();
    const calls = mockFetch(handlers([({ path, method, body }) => (path === "/warehouse/credentials/read" && method === "POST" ? { ...WRITE, id: 4, credential_kind: "read", key_id: (body as { key_id: string }).key_id } : undefined)]));
    renderRoutes(routes, "/warehouse");
    const user = userEvent.setup();

    expect(await screen.findByText("docs")).toBeInTheDocument(); // status resolved → default root path is /apps/x
    const form = screen.getByRole("form", { name: "新增读凭证" });
    await user.type(within(form).getByLabelText("新增读凭证 Access Key ID"), "AKREAD");
    await user.type(within(form).getByLabelText("新增读凭证 Secret"), "s3cret");
    await user.click(within(form).getByRole("button", { name: "添加读凭证" }));

    await waitFor(() => expect(calls.find((call) => call.method === "POST" && call.url === "/warehouse/credentials/read")?.body).toEqual({ key_id: "AKREAD", key_secret: "s3cret", root_path: "/apps/x" }));
  });

  it("uploads files as multipart to the chosen target directory", async () => {
    loginAs();
    const calls = mockFetch(handlers([({ path, method }) => (path === "/warehouse/upload" && method === "POST" ? { warehouse_path: "/apps/x/uploads/demo.md", file_name: "demo.md", size: 3, uploaded_at: "2026-01-01T00:00:00" } : undefined)]));
    renderRoutes(routes, "/warehouse");
    const user = userEvent.setup();

    expect(await screen.findByText("docs")).toBeInTheDocument(); // status + credentials resolved
    const input = screen.getByLabelText("选择文件") as HTMLInputElement;
    await waitFor(() => expect(input).toBeEnabled());
    await user.upload(input, new File(["abc"], "demo.md", { type: "text/markdown" }));
    await user.click(screen.getByRole("button", { name: /上传 1 个文件/ }));

    await waitFor(() => expect(calls.some((call) => call.url === "/warehouse/upload")).toBe(true));
    const body = calls.find((call) => call.url === "/warehouse/upload")!.body as FormData;
    expect(body).toBeInstanceOf(FormData);
    expect(body.get("target_dir")).toBe("/apps/x/uploads");
    expect((body.get("file") as File).name).toBe("demo.md");
    // Both the inline batch summary and the toast report the result.
    expect(await screen.findAllByText(/已上传 1 个文件/)).toHaveLength(2);
  });

  it("deletes the write credential after confirmation and browses the app root", async () => {
    loginAs();
    const calls = mockFetch(handlers([({ path, method }) => (path === "/warehouse/credentials/write" && method === "DELETE" ? { ok: true } : undefined)]));
    renderRoutes(routes, "/warehouse");
    const user = userEvent.setup();

    expect(await screen.findByText("docs")).toBeInTheDocument(); // browser used the write credential
    await user.click(screen.getByRole("button", { name: "删除" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "删除" }));
    await waitFor(() => expect(calls.some((call) => call.method === "DELETE" && call.url === "/warehouse/credentials/write")).toBe(true));
  });
});
