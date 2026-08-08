export type Health = { status: string };

const jsonHeaders = { "Content-Type": "application/json" };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { ...jsonHeaders, ...(init?.headers ?? {}) } });
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),
  listKnowledgeBases: () => request<unknown[]>("/kbs"),
};
