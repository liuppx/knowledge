import { vi } from "vitest";

export type Captured = { method: string; url: string; body: unknown };
export type Handler = (ctx: { method: string; url: string; body: unknown; path: string }) => unknown | Response | undefined;

export function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/**
 * Installs a fetch mock. `handlers` are tried in order; the first non-undefined
 * return wins (a Response is used as-is, anything else is JSON 200). Unhandled
 * requests return 404 so a missing stub fails loudly instead of hanging.
 */
export function mockFetch(handlers: Handler[]) {
  const calls: Captured[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    const rawBody = init?.body;
    const body = typeof rawBody === "string" ? JSON.parse(rawBody) : (rawBody ?? null);
    calls.push({ method, url, body });
    const path = url.split("?")[0];
    for (const handler of handlers) {
      const result = handler({ method, url, body, path });
      if (result === undefined) continue;
      return result instanceof Response ? result : json(result);
    }
    return json({ detail: `unhandled ${method} ${url}` }, 404);
  });
  return calls;
}

export const KB = (id: number, name = `KB ${id}`) => ({
  id,
  name,
  description: "",
  status: "active",
  retrieval_config: { chunk_size: 800 },
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
});

export const WORKBENCH = (kbId: number, overrides: Record<string, unknown> = {}) => ({
  kb_id: kbId,
  kb_name: `KB ${kbId}`,
  kb_description: "",
  kb_status: "active",
  stats: { kb_id: kbId, bindings_count: 0, documents_count: 0, chunks_count: 0, latest_task_status: null, latest_task_finished_at: null },
  binding_status_counts: { total: 0, enabled: 0, disabled: 0, indexed: 0, syncing: 0, failed: 0, pending_sync: 0 },
  bindings: [],
  recent_tasks: [],
  ...overrides,
});
