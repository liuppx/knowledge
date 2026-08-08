import type { TokenPair } from "./api";

const ACCESS_TOKEN_KEY = "knowledge:access-token";
const WALLET_ADDRESS_KEY = "knowledge:wallet-address";

export function saveSession(token: TokenPair) {
  localStorage.setItem(ACCESS_TOKEN_KEY, token.access_token);
  localStorage.setItem(WALLET_ADDRESS_KEY, token.wallet_address);
}

export function readSession() {
  const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY);
  const walletAddress = localStorage.getItem(WALLET_ADDRESS_KEY);
  return accessToken && walletAddress ? { accessToken, walletAddress } : null;
}

export function clearSession() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(WALLET_ADDRESS_KEY);
}
