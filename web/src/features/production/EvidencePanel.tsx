import { useState } from "react";

import { messageFor } from "../../api/client";
import type { Scope } from "../../api/endpoints/production";
import { useBuildEvidenceMutation, useEvidenceDetailQuery, useEvidenceQuery, useGenerateCandidatesMutation, useReindexUnitsMutation } from "../../api/queries/production";
import { Badge, DataTable, Drawer, EmptyState, ErrorState, LoadingState, formatDateTime, useToast } from "../../ui";
import { ScopePicker } from "./ScopePicker";

export function excerpt(text: string, max = 160): string {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > max ? `${clean.slice(0, max)}…` : clean;
}

type Props = { kbId: number; selectedEvidenceId: number | null; onSelectEvidence: (id: number | null) => void; onCandidatesGenerated: () => void };

export function EvidencePanel({ kbId, selectedEvidenceId, onSelectEvidence, onCandidatesGenerated }: Props) {
  const toast = useToast();
  const [scope, setScope] = useState<Scope | null>(null);
  const [vectorStatus, setVectorStatus] = useState("");
  const [evidenceType, setEvidenceType] = useState("");
  const filters = {
    source_id: scope?.kind === "source" ? scope.id : null,
    asset_id: scope?.kind === "asset" ? scope.id : null,
    vector_status: vectorStatus || null,
    evidence_type: evidenceType.trim() || null,
  };
  const evidence = useEvidenceQuery(kbId, filters);
  const detail = useEvidenceDetailQuery(kbId, selectedEvidenceId);
  const build = useBuildEvidenceMutation(kbId);
  const generate = useGenerateCandidatesMutation(kbId);
  const reindex = useReindexUnitsMutation(kbId);

  async function runBuild() {
    if (!scope) return;
    try {
      const result = await build.mutateAsync(scope);
      toast.success(`已构建 ${result.built_evidence_count} 条 Evidence（处理 ${result.processed_asset_count} 个资产，跳过 ${result.skipped_asset_count}${result.failed_asset_ids?.length ? `，失败 ${result.failed_asset_ids.length}` : ""}）`);
    } catch (cause) {
      toast.error(messageFor(cause, "构建 Evidence 失败"));
    }
  }

  async function runGenerate() {
    if (!scope) return;
    try {
      const result = await generate.mutateAsync(scope);
      toast.success(`已生成 ${result.created_count} 条候选（复用 ${result.reused_count}），请到「候选审核」处理`);
      onCandidatesGenerated();
    } catch (cause) {
      toast.error(messageFor(cause, "生成候选失败"));
    }
  }

  async function runReindex() {
    try {
      const result = await reindex.mutateAsync();
      const weaviate = result.weaviate ? ` · Weaviate ${String(result.weaviate.status ?? "")}` : "";
      toast.success(`单元向量已回填：新增 ${result.indexed}，未变更 ${result.skipped}${weaviate}`);
    } catch (cause) {
      toast.error(messageFor(cause, "回填失败"));
    }
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Evidence</h2>
        <button type="button" className="outline-button" onClick={() => void runReindex()} disabled={reindex.isPending} title="为混合检索回填单元级向量（幂等）">
          {reindex.isPending ? "回填中…" : "回填向量索引"}
        </button>
      </div>
      <p className="muted">Evidence 是从资产中抽取的可引用证据单元；先按来源或资产构建，再生成候选知识项。</p>
      <div className="toolbar">
        <ScopePicker kbId={kbId} value={scope} onChange={setScope} />
        <div className="actions">
          <button type="button" className="primary-button" onClick={() => void runBuild()} disabled={!scope || build.isPending}>
            {build.isPending ? "构建中…" : "构建 Evidence"}
          </button>
          <button type="button" className="outline-button" onClick={() => void runGenerate()} disabled={!scope || generate.isPending}>
            {generate.isPending ? "生成中…" : "生成候选"}
          </button>
        </div>
      </div>
      <div className="toolbar">
        <select aria-label="向量状态" value={vectorStatus} onChange={(event) => setVectorStatus(event.target.value)}>
          <option value="">全部向量状态</option>
          <option value="pending">pending</option>
          <option value="indexed">indexed</option>
          <option value="failed">failed</option>
        </select>
        <input value={evidenceType} onChange={(event) => setEvidenceType(event.target.value)} placeholder="evidence_type 过滤" aria-label="Evidence 类型" />
      </div>
      {evidence.isLoading ? <LoadingState /> : null}
      {evidence.isError ? <ErrorState error={evidence.error} fallback="加载 Evidence 失败" onRetry={() => void evidence.refetch()} /> : null}
      {evidence.data ? (
        <DataTable
          rows={evidence.data}
          rowKey={(unit) => unit.id}
          selectedKey={selectedEvidenceId}
          onRowClick={(unit) => onSelectEvidence(unit.id)}
          empty={<EmptyState title="还没有 Evidence" description="选择一个来源或资产并点击「构建 Evidence」。来源需先在「资产与导入」中扫描出资产。" />}
          columns={[
            { key: "id", header: "#", width: "70px", render: (unit) => unit.id },
            { key: "type", header: "类型", width: "110px", render: (unit) => unit.evidence_type },
            { key: "text", header: "内容", render: (unit) => <span title={unit.text}>{excerpt(unit.text)}</span> },
            { key: "asset", header: "资产", width: "80px", align: "right", render: (unit) => `#${unit.asset_id}` },
            { key: "vector", header: "向量", width: "100px", render: (unit) => <Badge status={unit.vector_status} /> },
            { key: "created", header: "创建", width: "160px", render: (unit) => formatDateTime(unit.created_at) },
          ]}
        />
      ) : null}
      <Drawer open={selectedEvidenceId !== null} title={`Evidence #${selectedEvidenceId ?? ""}`} onClose={() => onSelectEvidence(null)} width={720}>
        {detail.isLoading ? <LoadingState /> : null}
        {detail.isError ? <ErrorState error={detail.error} fallback="加载 Evidence 失败" /> : null}
        {detail.data ? (
          <>
            <div className="actions" style={{ marginBottom: 10 }}>
              <Badge status={detail.data.vector_status} />
              <span className="muted">
                {detail.data.evidence_type} · 资产 #{detail.data.asset_id} · {formatDateTime(detail.data.created_at)}
              </span>
            </div>
            <p className="evidence-text">{detail.data.text}</p>
            <h3 style={{ margin: "14px 0 6px" }}>来源定位</h3>
            <pre className="pre-json">{JSON.stringify(detail.data.source_locator ?? {}, null, 2)}</pre>
            {detail.data.metadata_json && Object.keys(detail.data.metadata_json).length ? (
              <>
                <h3 style={{ margin: "14px 0 6px" }}>元数据</h3>
                <pre className="pre-json">{JSON.stringify(detail.data.metadata_json, null, 2)}</pre>
              </>
            ) : null}
          </>
        ) : null}
      </Drawer>
    </section>
  );
}
