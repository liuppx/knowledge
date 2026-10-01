import { afterEach, describe, expect, it, vi } from "vitest";

import { SESSION_EXPIRED_EVENT, readSession, saveSession } from "../features/auth/session";
import { ApiError, buildUrl, errorMessageFrom, request } from "./client";

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("request", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends the bearer token and parses JSON", async () => {
    saveSession({ access_token: "a1", refresh_token: "r1", wallet_address: "0xabc" });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(200, [{ id: 1 }]));

    const result = await request<{ id: number }[]>("/kbs", { query: { page: 2, empty: "" } });

    expect(result).toEqual([{ id: 1 }]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/kbs?page=2");
    expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer a1");
  });

  it("refreshes once on 401 and retries with the new token", async () => {
    saveSession({ access_token: "old", refresh_token: "r1", wallet_address: "0xabc" });
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(401, { detail: "expired" }))
      .mockResolvedValueOnce(jsonResponse(200, { access_token: "new", refresh_token: "r2", wallet_address: "0xabc" }))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));

    await expect(request("/kbs/1")).resolves.toEqual({ ok: true });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toBe("/auth/refresh");
    expect((fetchMock.mock.calls[2][1]?.headers as Record<string, string>).Authorization).toBe("Bearer new");
    expect(readSession()?.accessToken).toBe("new");
  });

  it("expires the session when refresh fails", async () => {
    saveSession({ access_token: "old", refresh_token: "r1", wallet_address: "0xabc" });
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(401, { detail: "expired" }))
      .mockResolvedValueOnce(jsonResponse(401, { detail: "refresh expired" }));
    const expired = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, expired);

    await expect(request("/kbs/1")).rejects.toMatchObject({ status: 401 });

    expect(expired).toHaveBeenCalledTimes(1);
    expect(readSession()).toBeNull();
  });

  it("surfaces FastAPI detail strings and validation lists", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(422, { detail: [{ loc: ["body", "name"], msg: "field required" }, { msg: "too short" }] }),
    );
    const error = await request("/kbs", { method: "POST", json: {} }).catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe("field required；too short");
    expect(errorMessageFrom({ detail: "nope" }, "x")).toBe("nope");
    expect(errorMessageFrom({}, "fallback")).toBe("fallback");
  });

  it("builds query strings without empty values", () => {
    expect(buildUrl("/a", { x: 1, y: undefined, z: null, w: "" })).toBe("/a?x=1");
    expect(buildUrl("/a?k=v", { x: true })).toBe("/a?k=v&x=true");
  });
});
