import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { documentsApi } from "../endpoints/documents";
import { kbKeys } from "./kbs";

export const documentKeys = {
  list: (kbId: number) => ["kbs", kbId, "documents"] as const,
  detail: (kbId: number, documentId: number) => ["kbs", kbId, "documents", documentId] as const,
};

export function useDocumentsQuery(kbId: number) {
  return useQuery({ queryKey: documentKeys.list(kbId), queryFn: () => documentsApi.list(kbId) });
}

export function useDocumentQuery(kbId: number, documentId: number | null) {
  return useQuery({
    queryKey: documentKeys.detail(kbId, documentId ?? 0),
    queryFn: () => documentsApi.get(kbId, documentId as number),
    enabled: documentId !== null,
  });
}

export function useDeleteDocumentMutation(kbId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (documentId: number) => documentsApi.remove(kbId, documentId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: documentKeys.list(kbId) });
      void client.invalidateQueries({ queryKey: kbKeys.stats(kbId) });
      void client.invalidateQueries({ queryKey: kbKeys.workbench(kbId) });
    },
  });
}
