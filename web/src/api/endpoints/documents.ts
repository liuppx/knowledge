import { request } from "../client";
import type { Schema } from "../types";

export type Document = Schema<"DocumentRead">;
export type DocumentDetail = Schema<"DocumentDetailRead">;
export type DocumentChunk = Schema<"DocumentChunkRead">;

export const documentsApi = {
  list: (kbId: number) => request<Document[]>(`/kbs/${kbId}/documents`),
  get: (kbId: number, documentId: number) => request<DocumentDetail>(`/kbs/${kbId}/documents/${documentId}`),
  remove: (kbId: number, documentId: number) => request<Schema<"OkResponse">>(`/kbs/${kbId}/documents/${documentId}`, { method: "DELETE" }),
};
