const LAST_KB_KEY = "knowledge:last-kb";

/** The KB the user was last working in; `/` redirects here so a refresh lands back in place. */
export function readLastKbId(): number | null {
  const raw = localStorage.getItem(LAST_KB_KEY);
  const value = raw ? Number(raw) : NaN;
  return Number.isInteger(value) && value > 0 ? value : null;
}

export function rememberKbId(kbId: number) {
  localStorage.setItem(LAST_KB_KEY, String(kbId));
}

export function forgetKbId(kbId?: number) {
  if (kbId === undefined || readLastKbId() === kbId) localStorage.removeItem(LAST_KB_KEY);
}
