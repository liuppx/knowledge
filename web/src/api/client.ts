export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const accessToken = localStorage.getItem("knowledge:access-token");
  const response = await fetch(path, {
    ...init,
    headers: { Accept: "application/json", ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}), ...(init?.headers ?? {}) },
  });
  const body = await response.text();
  const data = body ? JSON.parse(body) : null;
  if (!response.ok) throw new ApiError(data?.detail ?? `${response.status} ${response.statusText}`, response.status);
  return data as T;
}
