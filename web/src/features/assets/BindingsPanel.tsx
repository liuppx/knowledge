import { useState } from "react";
import { Link } from "react-router-dom";

import { messageFor } from "../../api/client";
import type { Binding } from "../../api/endpoints/warehouse";
import type { TaskType } from "../../api/endpoints/tasks";
import { TASK_TYPE_LABELS } from "../../api/endpoints/tasks";
import { useCreateTaskFromBindingsMutation } from "../../api/queries/tasks";
import { useBindingsQuery, useCreateBindingMutation, useDeleteBindingMutation, useUpdateBindingMutation } from "../../api/queries/warehouse";
import { Badge, ConfirmDialog, DataTable, Drawer, EmptyState, ErrorState, LoadingState, formatRelative, useToast } from "../../ui";
import { WarehouseBrowser, type PickedPath } from "../warehouse/WarehouseBrowser";

type Confirm = { kind: "unbind"; binding: Binding } | { kind: "delete-index"; bindingIds: number[]; label: string } | null;

export function BindingsPanel({ kbId, appRoot, onTaskCreated }: { kbId: number; appRoot: string; onTaskCreated?: (taskId: number) => void }) {
  const toast = useToast();
  const bindings = useBindingsQuery(kbId);
  const create = useCreateBindingMutation(kbId);
  const update = useUpdateBindingMutation(kbId);
  const remove = useDeleteBindingMutation(kbId);
  const createTask = useCreateTaskFromBindingsMutation(kbId);
  const [picking, setPicking] = useState(false);
  const [confirm, setConfirm] = useState<Confirm>(null);

  const rows = bindings.data ?? [];
  const enabledCount = rows.filter((binding) => binding.enabled).length;

  async function bind(picked: PickedPath) {
    try {
      const binding = await create.mutateAsync({ source_path: picked.path, scope_type: picked.scope, credential_id: picked.access.credentialId ?? null });
      setPicking(false);
      toast.success(`已绑定 ${binding.source_path}`);
    } catch (cause) {
      toast.error(messageFor(cause, "绑定失败"));
    }
  }

  async function runTask(type: TaskType, bindingIds: number[], label: string) {
    if (type === "delete") {
      setConfirm({ kind: "delete-index", bindingIds, label });
      return;
    }
    await submitTask(type, bindingIds);
  }

  async function submitTask(type: TaskType, bindingIds: number[]) {
    try {
      const task = await createTask.mutateAsync({ type, payload: { binding_ids: bindingIds } });
      toast.success(`${TASK_TYPE_LABELS[type]}任务 #${task.id} 已创建`);
      onTaskCreated?.(task.id);
    } catch (cause) {
      toast.error(messageFor(cause, "创建任务失败"));
    }
  }

  async function toggle(binding: Binding, enabled: boolean) {
    try {
      await update.mutateAsync({ bindingId: binding.id, payload: { enabled } });
    } catch (cause) {
      toast.error(messageFor(cause, "更新绑定失败"));
    }
  }

  async function onConfirm() {
    if (!confirm) return;
    try {
      if (confirm.kind === "unbind") {
        await remove.mutateAsync(confirm.binding.id);
        toast.success("已解绑");
      } else {
        await submitTask("delete", confirm.bindingIds);
      }
    } catch (cause) {
      toast.error(messageFor(cause, "操作失败"));
    } finally {
      setConfirm(null);
    }
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Warehouse 绑定</h2>
        <div className="actions">
          <button type="button" className="outline-button" onClick={() => void runTask("import", [], "全部启用绑定")} disabled={!enabledCount || createTask.isPending}>
            导入全部启用绑定
          </button>
          <button type="button" className="outline-button" onClick={() => void runTask("reindex", [], "全部启用绑定")} disabled={!enabledCount || createTask.isPending}>
            重建全部
          </button>
          <button type="button" className="primary-button" onClick={() => setPicking(true)}>
            绑定新路径
          </button>
        </div>
      </div>
      <p className="muted">绑定是知识库与 Warehouse 目录/文件的长期关系，使用读凭证；之后可按绑定批量导入、重建或删除索引。</p>
      {bindings.isLoading ? <LoadingState /> : null}
      {bindings.isError ? <ErrorState error={bindings.error} fallback="加载绑定失败" onRetry={() => void bindings.refetch()} /> : null}
      {bindings.data ? (
        <DataTable
          rows={rows}
          rowKey={(binding) => binding.id}
          empty={
            <EmptyState
              title="还没有绑定"
              description="先在 Warehouse 页配置读凭证，再从目录树中选择要导入的目录或文件。"
              action={
                <div className="actions">
                  <button type="button" className="primary-button" onClick={() => setPicking(true)}>
                    绑定新路径
                  </button>
                  <Link className="text-link" to="/warehouse">
                    去配置凭证 →
                  </Link>
                </div>
              }
            />
          }
          columns={[
            {
              key: "path",
              header: "路径",
              render: (binding) => (
                <div>
                  <span className="mono ellipsis">{binding.source_path}</span>
                  <span className="muted">
                    {binding.scope_type} · {binding.credential_key_id ? `读凭证 ${binding.credential_key_id}` : "未关联凭证"}
                  </span>
                </div>
              ),
            },
            {
              key: "enabled",
              header: "启用",
              width: "70px",
              render: (binding) => (
                <input type="checkbox" checked={binding.enabled} onChange={(event) => void toggle(binding, event.target.checked)} aria-label={`启用 ${binding.source_path}`} />
              ),
            },
            {
              key: "sync",
              header: "同步",
              width: "120px",
              render: (binding) => <Badge status={binding.enabled ? binding.sync_status : "disabled"} title={binding.status_reason ?? undefined} />,
            },
            { key: "docs", header: "文档 / Chunk", width: "110px", align: "right", render: (binding) => `${binding.document_count} / ${binding.chunk_count}` },
            {
              key: "task",
              header: "最近任务",
              width: "150px",
              render: (binding) =>
                binding.latest_task_id ? (
                  <span>
                    <Badge status={binding.latest_task_status} /> <span className="muted">#{binding.latest_task_id} · {formatRelative(binding.latest_task_finished_at ?? binding.last_imported_at)}</span>
                  </span>
                ) : (
                  <span className="muted">—</span>
                ),
            },
            {
              key: "actions",
              header: "",
              width: "260px",
              align: "right",
              render: (binding) => (
                <div className="actions">
                  <button type="button" className="outline-button" onClick={() => void runTask("import", [binding.id], binding.source_path)} disabled={!binding.enabled}>
                    导入
                  </button>
                  <button type="button" className="outline-button" onClick={() => void runTask("reindex", [binding.id], binding.source_path)} disabled={!binding.enabled}>
                    重建
                  </button>
                  <button type="button" className="outline-button" onClick={() => void runTask("delete", [binding.id], binding.source_path)}>
                    删除索引
                  </button>
                  <button type="button" className="outline-button" onClick={() => setConfirm({ kind: "unbind", binding })} aria-label={`解绑 ${binding.source_path}`}>
                    解绑
                  </button>
                </div>
              ),
            },
          ]}
        />
      ) : null}
      <Drawer open={picking} title="选择要绑定的目录或文件" onClose={() => setPicking(false)} width={760}>
        <WarehouseBrowser initialPath={appRoot} onPick={(picked) => void bind(picked)} pickLabel="绑定此目录" />
      </Drawer>
      <ConfirmDialog
        open={confirm !== null}
        title={confirm?.kind === "unbind" ? "解绑源路径？" : "按绑定源删除索引？"}
        description={
          confirm?.kind === "unbind"
            ? "解绑后不会删除 Warehouse 原文件，但后续不会继续从该路径导入。"
            : `将为 ${confirm?.kind === "delete-index" ? confirm.bindingIds.length || enabledCount : 0} 个绑定源创建删除任务并清理对应已索引文档；Warehouse 原文件不会被删除。`
        }
        confirmLabel={confirm?.kind === "unbind" ? "解绑" : "创建删除任务"}
        danger
        busy={remove.isPending || createTask.isPending}
        onConfirm={() => void onConfirm()}
        onCancel={() => setConfirm(null)}
      />
    </section>
  );
}
