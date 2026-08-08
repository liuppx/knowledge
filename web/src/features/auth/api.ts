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
