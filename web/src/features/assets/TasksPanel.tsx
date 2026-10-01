import { FormEvent, useState } from "react";

import { messageFor } from "../../api/client";
import { RETRYABLE_TASK_STATUSES, TASK_TYPE_LABELS, describeTaskQueue, isTaskActive, type Task, type TaskType } from "../../api/endpoints/tasks";
import { useCancelTaskMutation, useCreateTaskMutation, useKbTasks, useProcessPendingMutation, useRetryTaskMutation, useTaskItemsQuery } from "../../api/queries/tasks";
import { useReadCredentialsQuery, useWriteCredentialQuery } from "../../api/queries/warehouse";
import { Badge, ConfirmDialog, DataTable, Drawer, EmptyState, ErrorState, LoadingState, formatDateTime, formatDuration, useToast } from "../../ui";

type Props = { kbId: number; selectedTaskId: number | null; onSelectTask: (taskId: number | null) => void; initialSourcePath?: string };

export function TasksPanel({ kbId, selectedTaskId, onSelectTask, initialSourcePath = "" }: Props) {
  const toast = useToast();
  const tasks = useKbTasks(kbId);
  const create = useCreateTaskMutation(kbId);
  const retry = useRetryTaskMutation();
  const cancel = useCancelTaskMutation();
  const processPending = useProcessPendingMutation();
  const readCredentials = useReadCredentialsQuery();
  const writeCredential = useWriteCredentialQuery();
  const [sourcePath, setSourcePath] = useState(initialSourcePath);
  const [credential, setCredential] = useState<string>("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const selected = tasks.kbTasks.find((task) => task.id === selectedTaskId) ?? null;

  async function submit(type: TaskType) {
    if (!sourcePath.trim() || create.isPending) return;
    try {
      const task = await create.mutateAsync({ type, payload: { source_paths: [sourcePath.trim()], credential_id: credential ? Number(credential) : null } });
      toast.success(`${TASK_TYPE_LABELS[type]}任务 #${task.id} 已创建`);
      onSelectTask(task.id);
    } catch (cause) {
      toast.error(messageFor(cause, "创建任务失败"));
    }
  }

  async function act(action: "retry" | "cancel", task: Task) {
    try {
      const updated = action === "retry" ? await retry.mutateAsync(task.id) : await cancel.mutateAsync(task.id);
      toast.success(action === "retry" ? `任务 #${task.id} 已重新排队` : `任务 #${updated.id} ${updated.status === "canceled" ? "已取消" : "取消中"}`);
    } catch (cause) {
      toast.error(messageFor(cause, "操作失败"));
    }
  }

  async function runPending() {
    try {
      const result = await processPending.mutateAsync();
      const message = String(result.message || "");
      toast.notify(message || `已处理 ${String(result.processed ?? 0)} 个任务，剩余排队 ${String(result.pending ?? 0)}`, message ? "warning" : "success");
    } catch (cause) {
      toast.error(messageFor(cause, "触发失败"));
    }
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>任务</h2>
        <div className="actions">
          {tasks.hasActive ? <Badge status="running">有任务进行中，每 3 秒刷新</Badge> : null}
          <button type="button" className="outline-button" onClick={() => void runPending()} disabled={processPending.isPending} title="没有常驻 worker 时手动处理一轮排队任务">
            处理排队任务
          </button>
        </div>
      </div>
      <form
        className="form-row"
        aria-label="创建任务"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          void submit("import");
        }}
      >
        <input value={sourcePath} onChange={(event) => setSourcePath(event.target.value)} placeholder="Warehouse 路径，例如 /apps/knowledge.yeying.pub/uploads/demo.md" aria-label="源路径" className="mono" />
        <select value={credential} onChange={(event) => setCredential(event.target.value)} aria-label="凭证">
          <option value="">默认凭证</option>
          {(readCredentials.data ?? []).map((item) => (
            <option key={item.id} value={item.id}>
              读凭证 · {item.key_id}
            </option>
          ))}
          {writeCredential.data?.credential ? <option value={writeCredential.data.credential.id}>写凭证 · {writeCredential.data.credential.key_id}</option> : null}
        </select>
        <div className="actions">
          <button type="submit" className="primary-button" disabled={!sourcePath.trim() || create.isPending}>
            导入
          </button>
          <button type="button" className="outline-button" onClick={() => void submit("reindex")} disabled={!sourcePath.trim() || create.isPending}>
            重建索引
          </button>
          <button type="button" className="outline-button" onClick={() => setConfirmDelete(true)} disabled={!sourcePath.trim() || create.isPending}>
            删除索引
          </button>
        </div>
      </form>
      {tasks.isLoading ? <LoadingState /> : null}
      {tasks.isError ? <ErrorState error={tasks.error} fallback="加载任务失败" onRetry={() => void tasks.refetch()} /> : null}
      {tasks.data ? (
        <DataTable
          rows={tasks.kbTasks}
          rowKey={(task) => task.id}
          selectedKey={selectedTaskId}
          onRowClick={(task) => onSelectTask(task.id)}
          empty={<EmptyState title="还没有任务" description="输入 Warehouse 路径创建导入任务，或在「绑定」页按绑定批量导入。" />}
          columns={[
            { key: "id", header: "#", width: "70px", render: (task) => task.id },
            { key: "type", header: "类型", width: "110px", render: (task) => TASK_TYPE_LABELS[task.task_type] ?? task.task_type },
            {
              key: "status",
              header: "状态",
              width: "220px",
              render: (task) => (
                <div>
                  <Badge status={task.status} />
                  <span className="muted" style={{ display: "block", marginTop: 2 }}>
                    {describeTaskQueue(task)}
                    {task.last_stage && isTaskActive(task.status) ? ` · ${task.last_stage}` : ""}
                  </span>
                </div>
              ),
            },
            { key: "paths", header: "来源", render: (task) => <span className="mono ellipsis" title={task.source_paths.join(", ")}>{task.source_paths.join(", ") || "—"}</span> },
            { key: "created", header: "创建", width: "160px", render: (task) => formatDateTime(task.created_at) },
            { key: "duration", header: "耗时", width: "90px", align: "right", render: (task) => formatDuration(task.run_duration_ms) },
            {
              key: "actions",
              header: "",
              width: "130px",
              align: "right",
              render: (task) => (
                <div className="actions" onClick={(event) => event.stopPropagation()}>
                  {task.cancelable ? (
                    <button type="button" className="outline-button" onClick={() => void act("cancel", task)} disabled={cancel.isPending}>
                      {task.status === "cancel_requested" ? "取消中" : "取消"}
                    </button>
                  ) : null}
                  {RETRYABLE_TASK_STATUSES.has(task.status) ? (
                    <button type="button" className="outline-button" onClick={() => void act("retry", task)} disabled={retry.isPending} aria-label={`重试任务 ${task.id}`}>
                      重试
                    </button>
                  ) : null}
                </div>
              ),
            },
          ]}
        />
      ) : null}
      <TaskDrawer task={selected} onClose={() => onSelectTask(null)} />
      <ConfirmDialog
        open={confirmDelete}
        title="删除该路径的索引？"
        description={`将为 ${sourcePath} 创建删除任务并清理对应已索引文档；Warehouse 原文件不会被删除。`}
        confirmLabel="创建删除任务"
        danger
        onConfirm={() => {
          setConfirmDelete(false);
          void submit("delete");
        }}
        onCancel={() => setConfirmDelete(false)}
      />
    </section>
  );
}

function TaskDrawer({ task, onClose }: { task: Task | null; onClose: () => void }) {
  const active = task ? isTaskActive(task.status) : false;
  const items = useTaskItemsQuery(task?.id ?? null, active);
  return (
    <Drawer open={task !== null} title={task ? `任务 #${task.id} · ${TASK_TYPE_LABELS[task.task_type] ?? task.task_type}` : ""} onClose={onClose} width={760}>
      {task ? (
        <>
          <dl className="detail-grid">
            <div>
              <dt>状态</dt>
              <dd>
                <Badge status={task.status} /> <span className="muted">{describeTaskQueue(task)}</span>
              </dd>
            </div>
            <div>
              <dt>阶段</dt>
              <dd>{task.last_stage ?? "—"}</dd>
            </div>
            <div>
              <dt>创建 / 开始 / 结束</dt>
              <dd>
                {formatDateTime(task.created_at)} / {formatDateTime(task.started_at)} / {formatDateTime(task.finished_at)}
              </dd>
            </div>
            <div>
              <dt>等待 / 执行耗时</dt>
              <dd>
                {formatDuration(task.wait_duration_ms)} / {formatDuration(task.run_duration_ms)}
              </dd>
            </div>
            <div>
              <dt>Worker</dt>
              <dd>{task.claimed_by ?? "—"} {task.heartbeat_at ? <span className="muted">· 心跳 {formatDateTime(task.heartbeat_at)}</span> : null}</dd>
            </div>
            <div>
              <dt>来源</dt>
              <dd className="mono">{task.source_paths.join(", ") || "—"}</dd>
            </div>
          </dl>
          {task.error_message ? (
            <p className="alert" role="alert">
              {task.error_message}
            </p>
          ) : null}
          {task.stats_json && Object.keys(task.stats_json).length ? <pre className="pre-json">{JSON.stringify(task.stats_json, null, 2)}</pre> : null}
          <h3 style={{ margin: "16px 0 8px" }}>文件明细</h3>
          {items.isLoading ? <LoadingState /> : null}
          {items.isError ? <ErrorState error={items.error} fallback="加载明细失败" /> : null}
          {items.data ? (
            <DataTable
              dense
              rows={items.data}
              rowKey={(item) => item.id}
              empty={<p className="muted state-row">暂无文件明细。</p>}
              columns={[
                { key: "file", header: "文件", render: (item) => <span className="ellipsis" title={item.source_path}>{item.file_name || item.source_path}</span> },
                { key: "status", header: "状态", width: "100px", render: (item) => <Badge status={item.status} /> },
                { key: "stage", header: "阶段", width: "110px", render: (item) => item.stage ?? "—" },
                { key: "chunks", header: "Chunk", width: "70px", align: "right", render: (item) => item.processed_chunks ?? 0 },
                { key: "duration", header: "耗时", width: "90px", align: "right", render: (item) => formatDuration(item.duration_ms) },
                { key: "message", header: "说明", render: (item) => <span className="muted">{[item.error_type, item.message].filter(Boolean).join(" · ") || "—"}</span> },
              ]}
            />
          ) : null}
        </>
      ) : null}
    </Drawer>
  );
}
