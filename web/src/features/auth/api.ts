import { request } from "../../api/client";
import type { Schema } from "../../api/types";

export type { TokenPair } from "./session";

export type PassportSession = Schema<"PassportSessionResponse">;
export type PassportSessionStatus = Schema<"PassportStatusResponse">;

export const passportApi = {
  createSession: () => request<PassportSession>("/auth/passport/sessions", { method: "POST" }),
  getSession: (sessionId: string) => request<PassportSessionStatus>(`/auth/passport/sessions/${encodeURIComponent(sessionId)}`),
  logout: () => request<unknown>("/auth/logout", { method: "POST" }).catch(() => undefined),
};

export function tokenFromLogin(response: unknown): Schema<"TokenResponse"> {
  if (!response || typeof response !== "object") throw new Error("钱包登录返回无效数据");
  const token = response as Partial<Schema<"TokenResponse">>;
  if (!token.access_token || !token.refresh_token || !token.wallet_address) throw new Error("钱包登录未返回会话信息");
  return token as Schema<"TokenResponse">;
}
