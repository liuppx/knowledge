import { useState } from "react";

import { messageFor } from "../../api/client";
import type { Document } from "../../api/endpoints/documents";
import { useDeleteDocumentMutation, useDocumentQuery, useDocumentsQuery } from "../../api/queries/documents";
import { Badge, ConfirmDialog, DataTable, Drawer, EmptyState, ErrorState, LoadingState, formatDateTime, useToast } from "../../ui";

export function DocumentsPanel({ kbId, onGoToTasks }: { kbId: number; onGoToTasks: () => void }) {
  const toast = useToast();
  const documents = useDocumentsQuery(kbId);
  const remove = useDeleteDocumentMutation(kbId);
  const [openId, setOpenId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<Document | null>(null);
  const detail = useDocumentQuery(kbId, openId);

  async function confirmDelete() {
    if (!deleting) return;
    try {
      await remove.mutateAsync(deleting.id);
      toast.success(`已删除 ${deleting.source_file_name} 的索引`);
      if (openId === deleting.id) setOpenId(null);
      setDeleting(null);
    } catch (cause) {
      toast.error(messageFor(cause, "删除失败"));
    }
  }

  return (
    <section className="panel">
      <h2>文档</h2>
      <p className="muted">导入任务产出的文档及其 chunk。文件级处理状态在这里可见；删除只移除索引，不动 Warehouse 原文件。</p>
      {documents.isLoading ? <LoadingState /> : null}
      {documents.isError ? <ErrorState error={documents.error} fallback="加载文档失败" onRetry={() => void documents.refetch()} /> : null}
      {documents.data ? (
        <DataTable
          rows={documents.data}
          rowKey={(document) => document.id}
          selectedKey={openId}
          onRowClick={(document) => setOpenId(document.id)}
          empty={
            <EmptyState
              title="还没有导入的文档"
              description="创建导入任务后，处理完成的文件会出现在这里。"
              action={
                <button type="button" className="primary-button" onClick={onGoToTasks}>
                  去创建导入任务
                </button>
              }
            />
          }
          columns={[
            {
              key: "name",
              header: "文件",
              render: (document) => (
                <div>
                  <strong>{document.source_file_name}</strong>
                  <span className="muted mono ellipsis">{document.source_path}</span>
                </div>
              ),
            },
            { key: "type", header: "类型", width: "90px", render: (document) => document.file_type },
            { key: "kind", header: "来源", width: "110px", render: (document) => document.source_kind },
            { key: "status", header: "处理状态", width: "110px", render: (document) => <Badge status={document.parse_status} /> },
            { key: "chunks", header: "Chunk", width: "80px", align: "right", render: (document) => document.chunk_count },
            { key: "indexed", header: "最近索引", width: "170px", render: (document) => formatDateTime(document.last_indexed_at) },
            {
              key: "actions",
              header: "",
              width: "80px",
              align: "right",
              render: (document) => (
                <div className="actions" onClick={(event) => event.stopPropagation()}>
                  <button type="button" className="outline-button" onClick={() => setDeleting(document)} aria-label={`删除 ${document.source_file_name}`}>
                    删除
                  </button>
                </div>
              ),
            },
          ]}
        />
      ) : null}
      <Drawer open={openId !== null} title={detail.data?.source_file_name ?? "文档详情"} onClose={() => setOpenId(null)} width={760}>
        {detail.isLoading ? <LoadingState /> : null}
        {detail.isError ? <ErrorState error={detail.error} fallback="加载文档失败" /> : null}
        {detail.data ? (
          <>
            <dl className="detail-grid">
              <div>
                <dt>路径</dt>
                <dd className="mono">{detail.data.source_path}</dd>
              </div>
              <div>
                <dt>状态</dt>
                <dd>
                  <Badge status={detail.data.parse_status} />
                </dd>
              </div>
              <div>
                <dt>版本</dt>
                <dd className="mono">{detail.data.source_etag_or_mtime ?? "—"}</dd>
              </div>
              <div>
                <dt>最近索引</dt>
                <dd>{formatDateTime(detail.data.last_indexed_at)}</dd>
              </div>
            </dl>
            <h3 style={{ margin: "16px 0 8px" }}>Chunk（{detail.data.chunks?.length ?? 0}）</h3>
            <div className="chunk-list">
              {(detail.data.chunks ?? []).map((chunk) => (
                <article key={chunk.id} className="chunk">
                  <header>
                    <span className="mono">#{chunk.chunk_index}</span>
                    <Badge status={chunk.index_status ?? "pending"} />
                    <span className="muted">{chunk.embedding_model ?? "未嵌入"}</span>
                  </header>
                  <p>{chunk.text}</p>
                  {chunk.metadata && Object.keys(chunk.metadata).length ? <pre className="pre-json">{JSON.stringify(chunk.metadata, null, 2)}</pre> : null}
                </article>
              ))}
            </div>
          </>
        ) : null}
      </Drawer>
      <ConfirmDialog
        open={deleting !== null}
        title={`删除「${deleting?.source_file_name ?? ""}」的索引？`}
        description="将移除该文档的 chunk 与向量；Warehouse 原文件保留，可随时重新导入。"
        confirmLabel="删除索引"
        danger
        busy={remove.isPending}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleting(null)}
      />
    </section>
  );
}
