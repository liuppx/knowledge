import { describe, expect, it } from "vitest";
import { tokenFromLogin } from "./api";

describe("tokenFromLogin", () => {
  it("requires the complete wallet identity token pair", () => {
    expect(tokenFromLogin({
      access_token: "access",
      token: "access",
      refresh_token: "refresh",
      wallet_address: "0x1111111111111111111111111111111111111111",
      expires_at: "2026-10-29T12:00:00Z",
      refresh_expires_at: "2026-11-05T12:00:00Z",
      did: "did:yeying:wid_test",
    })).toMatchObject({ access_token: "access", refresh_token: "refresh", did: "did:yeying:wid_test" });
  });

  it("rejects incomplete login responses", () => {
    expect(() => tokenFromLogin({ token: "access" })).toThrow("钱包登录未返回会话信息");
  });
});
