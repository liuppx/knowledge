const ACCESS_TOKEN_KEY = "knowledge:access-token";
const REFRESH_TOKEN_KEY = "knowledge:refresh-token";
const WALLET_ADDRESS_KEY = "knowledge:wallet-address";
const EXPIRES_AT_KEY = "knowledge:expires-at";

export type TokenPair = {
  access_token: string;
  refresh_token?: string | null;
  wallet_address: string;
  expires_at?: string | null;
  refresh_expires_at?: string | null;
};

export type StoredSession = {
  accessToken: string;
  refreshToken: string | null;
  walletAddress: string;
  expiresAt: string | null;
};

/** Fired on window when the session can no longer be refreshed; the app routes to /login. */
export const SESSION_EXPIRED_EVENT = "knowledge:session-expired";

export function saveSession(token: TokenPair) {
  localStorage.setItem(ACCESS_TOKEN_KEY, token.access_token);
  localStorage.setItem(WALLET_ADDRESS_KEY, token.wallet_address);
  if (token.refresh_token) localStorage.setItem(REFRESH_TOKEN_KEY, token.refresh_token);
  if (token.expires_at) localStorage.setItem(EXPIRES_AT_KEY, token.expires_at);
}

export function readSession(): StoredSession | null {
  const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY);
  const walletAddress = localStorage.getItem(WALLET_ADDRESS_KEY);
  if (!accessToken || !walletAddress) return null;
  return {
    accessToken,
    walletAddress,
    refreshToken: localStorage.getItem(REFRESH_TOKEN_KEY),
    expiresAt: localStorage.getItem(EXPIRES_AT_KEY),
  };
}

export function clearSession() {
  for (const key of [ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY, WALLET_ADDRESS_KEY, EXPIRES_AT_KEY]) localStorage.removeItem(key);
}

export function expireSession() {
  clearSession();
  window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
}
