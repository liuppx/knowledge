import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { useKbWorkbenchQuery } from "../../api/queries/kbs";
import { useKbId } from "../../app/kbRoute";
import { Badge, DataTable, EmptyState, ErrorState, LoadingState, formatDateTime } from "../../ui";

export function OverviewPage() {
  const kbId = useKbId();
  const workbench = useKbWorkbenchQuery(kbId);

  if (workbench.isLoading) return <LoadingState />;
  if (workbench.isError || !workbench.data) return <ErrorState error={workbench.error} fallback="加载知识库概览失败" onRetry={() => void workbench.refetch()} />;
  const data = workbench.data;
  const counts = data.binding_status_counts;

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Overview</p>
          <h1>{data.kb_name}</h1>
          <p className="muted">{data.kb_description || "暂无描述"}</p>
        </div>
        <Badge status={data.kb_status} />
      </header>
      <div className="metric-grid">
        <Metric label="绑定目录" value={data.stats.bindings_count} />
        <Metric label="文档" value={data.stats.documents_count} />
        <Metric label="Chunk" value={data.stats.chunks_count} />
        <Metric label="最近任务" value={<Badge status={data.stats.latest_task_status} />} hint={formatDateTime(data.stats.latest_task_finished_at)} />
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>绑定状态</h2>
          <Link className="text-link" to={`/kbs/${kbId}/assets`}>
            管理资产与导入 →
          </Link>
        </div>
        <div className="chip-row">
          <span>共 {counts.total}</span>
          <span>启用 {counts.enabled}</span>
          <span>已索引 {counts.indexed}</span>
          <span>同步中 {counts.syncing}</span>
          <span>待同步 {counts.pending_sync}</span>
          <span>失败 {counts.failed}</span>
        </div>
      </section>
      <section className="panel">
        <h2>最近任务</h2>
        <DataTable
          rows={data.recent_tasks}
          rowKey={(task) => task.id}
          empty={
            <EmptyState
              title="还没有导入任务"
              description="在「资产与导入」绑定 Warehouse 目录或上传文件后创建导入任务。"
              action={<Link className="primary-button" to={`/kbs/${kbId}/assets`}>去导入</Link>}
            />
          }
          columns={[
            { key: "id", header: "#", render: (task) => task.id, width: "70px" },
            { key: "type", header: "类型", render: (task) => task.task_type, width: "140px" },
            { key: "status", header: "状态", render: (task) => <Badge status={task.status} />, width: "120px" },
            { key: "paths", header: "来源", render: (task) => <span className="muted ellipsis">{task.source_paths.join(", ") || "—"}</span> },
            { key: "finished", header: "完成时间", render: (task) => formatDateTime(task.finished_at ?? task.created_at), width: "180px" },
          ]}
        />
      </section>
    </>
  );
}

function Metric({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="metric">
      <strong>{value}</strong>
      <span>
        {label}
        {hint && hint !== "—" ? ` · ${hint}` : ""}
      </span>
    </div>
  );
}
