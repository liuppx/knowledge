import { expireSession, readSession, saveSession, type TokenPair } from "../features/auth/session";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type QueryParams = Record<string, string | number | boolean | null | undefined>;

export type RequestOptions = Omit<RequestInit, "body"> & {
  /** JSON body; sets Content-Type and serialises. Use `body` for FormData. */
  json?: unknown;
  body?: BodyInit | null;
  query?: QueryParams;
  /** Internal: set after one refresh attempt so a 401 cannot loop. */
  skipRefresh?: boolean;
};

export function buildUrl(path: string, query?: QueryParams): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const encoded = params.toString();
  return encoded ? `${path}${path.includes("?") ? "&" : "?"}${encoded}` : path;
}

/** FastAPI puts errors in `detail`: a string, or a list of validation errors. */
export function errorMessageFrom(data: unknown, fallback: string): string {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string" && detail) return detail;
    if (Array.isArray(detail)) {
      const parts = detail
        .map((item) => (item && typeof item === "object" && "msg" in item ? String((item as { msg: unknown }).msg) : ""))
        .filter(Boolean);
      if (parts.length) return parts.join("；");
    }
  }
  return fallback;
}

let refreshing: Promise<boolean> | null = null;

/** One refresh at a time; concurrent 401s share the same attempt. */
async function refreshAccessToken(): Promise<boolean> {
  const session = readSession();
  if (!session?.refreshToken) return false;
  if (!refreshing) {
    refreshing = fetch("/auth/refresh", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: session.refreshToken }),
    })
      .then(async (response) => {
        if (!response.ok) return false;
        saveSession((await response.json()) as TokenPair);
        return true;
      })
      .catch(() => false)
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

function parseBody(text: string): unknown {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { json, query, headers, skipRefresh, ...init } = options;
  const session = readSession();
  const response = await fetch(buildUrl(path, query), {
    ...init,
    headers: {
      Accept: "application/json",
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(session ? { Authorization: `Bearer ${session.accessToken}` } : {}),
      ...(headers ?? {}),
    },
    body: json !== undefined ? JSON.stringify(json) : init.body,
  });

  if (response.status === 401 && session && !skipRefresh) {
    if (await refreshAccessToken()) return request<T>(path, { ...options, skipRefresh: true });
    expireSession();
  }

  const data = parseBody(await response.text());
  if (!response.ok) {
    throw new ApiError(errorMessageFrom(data, `${response.status} ${response.statusText}`.trim()), response.status, data);
  }
  return data as T;
}

export function messageFor(cause: unknown, fallback: string): string {
  return cause instanceof Error && cause.message ? cause.message : fallback;
}
