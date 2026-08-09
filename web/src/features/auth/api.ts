import { request } from "../../api/client";

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  wallet_address: string;
  expires_at: string;
  refresh_expires_at: string;
};

export type PassportSession = { session_id: string; verify_url: string; status: string; expires_at: string };
export type PassportSessionStatus = { status: string; token: TokenPair | null };

export const passportApi = {
  createSession: () => request<PassportSession>("/auth/passport/sessions", { method: "POST" }),
  getSession: (sessionId: string) => request<PassportSessionStatus>(`/auth/passport/sessions/${encodeURIComponent(sessionId)}`),
};

export function tokenFromLogin(response: unknown): TokenPair {
  if (!response || typeof response !== "object") throw new Error("钱包登录返回无效数据");
  const token = response as Partial<TokenPair>;
  if (!token.access_token || !token.refresh_token || !token.wallet_address) throw new Error("钱包登录未返回会话信息");
  return token as TokenPair;
}
