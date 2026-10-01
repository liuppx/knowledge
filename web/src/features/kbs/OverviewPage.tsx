import { useState, type ReactNode } from "react";
import { Settings, Trash2 } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { useKbQuery, useKbWorkbenchQuery } from "../../api/queries/kbs";
import { useCurrentReleaseQuery } from "../../api/queries/releases";
import { useKbId } from "../../app/kbRoute";
import { Badge, DataTable, EmptyState, ErrorState, LoadingState, formatDateTime, formatRelative } from "../../ui";
import { KbManageDialogs } from "./KbManageDialogs";

export function OverviewPage() {
  const kbId = useKbId();
  const navigate = useNavigate();
  const workbench = useKbWorkbenchQuery(kbId);
  const kb = useKbQuery(kbId);
  const release = useCurrentReleaseQuery(kbId);
  const [dialog, setDialog] = useState<"edit" | "delete" | null>(null);

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
        <div className="actions">
          <Badge status={data.kb_status} />
          <button type="button" className="outline-button" onClick={() => setDialog("edit")} disabled={!kb.data}>
            <Settings size={15} /> 设置
          </button>
          <button type="button" className="outline-button" onClick={() => setDialog("delete")} disabled={!kb.data} aria-label="删除知识库">
            <Trash2 size={15} />
          </button>
        </div>
      </header>

      <div className="metric-grid">
        <Metric label="绑定目录" value={data.stats.bindings_count} />
        <Metric label="文档" value={data.stats.documents_count} />
        <Metric label="Chunk" value={data.stats.chunks_count} />
        <Metric label="最近任务" value={<Badge status={data.stats.latest_task_status} />} hint={formatRelative(data.stats.latest_task_finished_at)} />
      </div>

      <div className="two-column">
        <section className="panel">
          <div className="panel-heading">
            <h2>当前发布</h2>
            <Link className="text-link" to={`/kbs/${kbId}/release`}>
              发布与授权 →
            </Link>
          </div>
          {release.isLoading ? <LoadingState /> : null}
          {release.isError ? <ErrorState error={release.error} fallback="加载发布信息失败" onRetry={() => void release.refetch()} /> : null}
          {release.data?.release ? (
            <dl className="detail-grid">
              <div>
                <dt>版本</dt>
                <dd>
                  <strong>{release.data.release.version}</strong> <Badge status={release.data.release.status} />
                </dd>
              </div>
              <div>
                <dt>发布时间</dt>
                <dd>{formatDateTime(release.data.release.published_at)}</dd>
              </div>
              <div>
                <dt>知识项</dt>
                <dd>{release.data.items?.length ?? 0}</dd>
              </div>
              <div>
                <dt>说明</dt>
                <dd className="muted">{release.data.release.release_note || "—"}</dd>
              </div>
            </dl>
          ) : null}
          {release.data === null ? (
            <EmptyState
              title="尚未发布"
              description="消费方（Chat / Agent / Project）只能检索已发布版本。审核知识项后在「发布与授权」发布第一个版本。"
              action={<Link className="primary-button" to={`/kbs/${kbId}/release`}>去发布</Link>}
            />
          ) : null}
        </section>

        <section className="panel">
          <div className="panel-heading">
            <h2>绑定状态</h2>
            <Link className="text-link" to={`/kbs/${kbId}/assets`}>
              资产与导入 →
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
          <DataTable
            dense
            rows={data.bindings}
            rowKey={(binding) => binding.id}
            empty={<p className="muted state-row">还没有绑定 Warehouse 目录。</p>}
            columns={[
              { key: "path", header: "路径", render: (binding) => <span className="mono ellipsis">{binding.source_path}</span> },
              { key: "sync", header: "同步", render: (binding) => <Badge status={binding.enabled ? binding.sync_status : "disabled"} />, width: "110px" },
              { key: "docs", header: "文档", render: (binding) => binding.document_count, width: "70px", align: "right" },
            ]}
          />
        </section>
      </div>

      <section className="panel">
        <h2>最近任务</h2>
        <DataTable
          rows={data.recent_tasks}
          rowKey={(task) => task.id}
          onRowClick={(task) => navigate(`/kbs/${kbId}/assets?task=${task.id}`)}
          empty={
            <EmptyState
              title="还没有导入任务"
              description="在「资产与导入」绑定 Warehouse 目录或上传文件后创建导入任务。"
              action={<Link className="primary-button" to={`/kbs/${kbId}/assets`}>去导入</Link>}
            />
          }
          columns={[
            { key: "id", header: "#", render: (task) => task.id, width: "70px" },
            { key: "type", header: "类型", render: (task) => task.task_type, width: "160px" },
            { key: "status", header: "状态", render: (task) => <Badge status={task.status} />, width: "120px" },
            { key: "paths", header: "来源", render: (task) => <span className="muted ellipsis">{task.source_paths.join(", ") || "—"}</span> },
            { key: "finished", header: "完成时间", render: (task) => formatDateTime(task.finished_at ?? task.created_at), width: "180px" },
          ]}
        />
      </section>

      <KbManageDialogs
        editing={dialog === "edit" ? (kb.data ?? null) : null}
        deleting={dialog === "delete" ? (kb.data ?? null) : null}
        onClose={() => setDialog(null)}
        onDeleted={() => navigate("/kbs", { replace: true })}
      />
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
