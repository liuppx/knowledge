import { describe, expect, it } from "vitest";
import { createIdentityLoginFetcher } from "./api";

describe("createIdentityLoginFetcher", () => {
  it("wraps raw FastAPI success responses in the SDK data envelope", async () => {
    const data = { audience: "http://127.0.0.1:8002", nonce: "nonce" };
    const fetcher = createIdentityLoginFetcher(async () => new Response(JSON.stringify(data)));

    const response = await fetcher("/auth/identity/login/session", { method: "POST" });

    expect(await response.json()).toEqual({ data });
  });

  it("does not wrap responses that already use an API envelope", async () => {
    const body = { code: 0, data: { audience: "http://127.0.0.1:8002" } };
    const fetcher = createIdentityLoginFetcher(async () => new Response(JSON.stringify(body)));

    const response = await fetcher("/auth/identity/login/session", { method: "POST" });

    expect(await response.json()).toEqual(body);
  });
});
