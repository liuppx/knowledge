import { useState } from "react";
import { Link } from "react-router-dom";

import { useFailuresQuery, useOpsOverviewQuery, useStoresHealthQuery, useWorkersQuery } from "../../api/endpoints/ops";
import { Badge, DataTable, EmptyState, ErrorState, LoadingState, formatDateTime, formatDuration, formatRelative } from "../../ui";

export function OpsPage() {
  const overview = useOpsOverviewQuery();
  const stores = useStoresHealthQuery();
  const workers = useWorkersQuery();
  const [traceId, setTraceId] = useState("");
  const failures = useFailuresQuery(traceId.trim());
  const data = overview.data;

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Operations</p>
          <h1>运维</h1>
          <p className="muted">队列与 worker 健康、依赖存储状态、最近失败任务。每 10 秒刷新。</p>
        </div>
      </header>

      {overview.isLoading ? <LoadingState /> : null}
      {overview.isError ? <ErrorState error={overview.error} fallback="加载概览失败" onRetry={() => void overview.refetch()} /> : null}
      {data ? (
        <>
          <div className="metric-grid">
            <Metric label="排队任务" value={data.tasks_pending} tone={data.tasks_pending ? "warning" : undefined} />
            <Metric label="执行中" value={data.tasks_running} />
            <Metric label="心跳过期的任务" value={data.tasks_claimed_stale} tone={data.tasks_claimed_stale ? "danger" : undefined} />
            <Metric label="平均等待 / 执行" value={`${formatDuration(data.avg_task_wait_ms)} / ${formatDuration(data.avg_task_run_ms)}`} />
          </div>
          <div className="metric-grid">
            <Metric label="知识库 / 文档 / Chunk" value={`${data.knowledge_bases} / ${data.documents} / ${data.chunks}`} />
            <Metric label="缺失 / 变更资产" value={`${data.source_assets_missing} / ${data.source_assets_stale}`} tone={data.source_assets_missing ? "danger" : data.source_assets_stale ? "warning" : undefined} />
            <Metric label="检索日志" value={data.retrieval_logs} />
            <Metric label="上传 / 任务总数" value={`${data.uploads} / ${data.tasks_total}`} />
          </div>
        </>
      ) : null}

      <div className="two-column">
        <section className="panel">
          <h2>依赖存储</h2>
          {stores.isLoading ? <LoadingState /> : null}
          {stores.isError ? <ErrorState error={stores.error} fallback="加载存储状态失败" onRetry={() => void stores.refetch()} /> : null}
          {stores.data ? (
            <dl className="detail-grid">
              <div>
                <dt>PostgreSQL</dt>
                <dd>
                  <Badge status={stores.data.database.startsWith("error") ? "error" : stores.data.database} />
                </dd>
              </div>
              <div>
                <dt>向量库（{stores.data.vector_store_mode}）</dt>
                <dd>
                  <Badge status={String(stores.data.vector_store_status?.status ?? "unknown").startsWith("error") ? "error" : String(stores.data.vector_store_status?.status ?? "unknown")} />
                </dd>
              </div>
              <div>
                <dt>模型网关（{stores.data.model_provider_mode}）</dt>
                <dd>
                  <Badge status={stores.data.model_provider_status} />
                </dd>
              </div>
              <div>
                <dt>对象存储</dt>
                <dd className="mono">
                  {stores.data.object_storage_endpoint} · {stores.data.object_storage_region}
                </dd>
              </div>
            </dl>
          ) : null}
          {stores.data?.vector_store_status && Object.keys(stores.data.vector_store_status).length > 1 ? <pre className="pre-json">{JSON.stringify(stores.data.vector_store_status, null, 2)}</pre> : null}
        </section>

        <section className="panel">
          <h2>Worker</h2>
          {workers.isLoading ? <LoadingState /> : null}
          {workers.isError ? <ErrorState error={workers.error} fallback="加载 worker 失败" onRetry={() => void workers.refetch()} /> : null}
          {workers.data ? (
            <DataTable
              dense
              rows={workers.data}
              rowKey={(worker) => worker.worker_name}
              empty={<EmptyState title="没有 worker 上报" description="启动 python -m knowledge.workers.runner（或 scripts/run_worker.sh）后会出现在这里；没有 worker 时可在任务页手动「处理排队任务」。" />}
              columns={[
                { key: "name", header: "名称", render: (worker) => <span className="mono">{worker.worker_name}</span> },
                { key: "status", header: "状态", width: "90px", render: (worker) => <Badge status={worker.status} /> },
                { key: "seen", header: "最近心跳", width: "110px", render: (worker) => formatRelative(worker.last_seen_at) },
                { key: "active", header: "进行中", width: "70px", align: "right", render: (worker) => worker.active_tasks_count },
                { key: "processed", header: "已处理", width: "70px", align: "right", render: (worker) => worker.processed_count },
                { key: "error", header: "最近错误", render: (worker) => <span className="muted ellipsis" title={worker.last_error ?? undefined}>{worker.last_error || "—"}</span> },
              ]}
            />
          ) : null}
        </section>
      </div>

      <section className="panel">
        <div className="panel-heading">
          <h2>最近失败任务</h2>
          <input value={traceId} onChange={(event) => setTraceId(event.target.value)} placeholder="按 trace_id 过滤" aria-label="trace_id" className="mono" />
        </div>
        {failures.isLoading ? <LoadingState /> : null}
        {failures.isError ? <ErrorState error={failures.error} fallback="加载失败任务失败" onRetry={() => void failures.refetch()} /> : null}
        {failures.data ? (
          <DataTable
            dense
            rows={failures.data}
            rowKey={(task) => task.id}
            empty={<p className="muted state-row">没有失败或部分成功的任务。</p>}
            columns={[
              { key: "id", header: "#", width: "70px", render: (task) => <Link to={`/kbs/${task.kb_id}/assets?task=${task.id}`}>{task.id}</Link> },
              { key: "kb", header: "知识库", width: "80px", render: (task) => <Link to={`/kbs/${task.kb_id}/overview`}>#{task.kb_id}</Link> },
              { key: "type", header: "类型", width: "90px", render: (task) => task.task_type },
              { key: "status", header: "状态", width: "110px", render: (task) => <Badge status={task.status} /> },
              { key: "trace", header: "trace_id", width: "150px", render: (task) => <span className="mono ellipsis" title={task.trace_id}>{task.trace_id || "—"}</span> },
              { key: "error", header: "错误", render: (task) => <span className="muted ellipsis" title={task.error_message}>{task.error_message || "—"}</span> },
              { key: "at", header: "结束", width: "160px", render: (task) => formatDateTime(task.finished_at ?? task.created_at) },
            ]}
          />
        ) : null}
      </section>
    </>
  );
}

function Metric({ label, value, tone }: { label: string; value: number | string; tone?: "warning" | "danger" }) {
  return (
    <div className={`metric${tone ? ` metric-${tone}` : ""}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
