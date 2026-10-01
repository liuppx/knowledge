import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { messageFor } from "../../api/client";
import { AVAILABILITY_MODES, RESULT_VIEWS, SEARCH_MODES, type SearchLabCompareResponse, type ServiceSearchResponse } from "../../api/endpoints/search";
import { useCompareMutation, useRetrievalLogQuery, useRetrievalLogsQuery, useSourceGovernanceQuery } from "../../api/queries/search";
import { useKbId } from "../../app/kbRoute";
import { Badge, DataTable, Drawer, EmptyState, ErrorState, LoadingState, formatDateTime, useToast } from "../../ui";
import { HitCard } from "./HitCard";
import { TraceView, collectSignals, signalTone } from "./TraceView";

export function SearchPage() {
  const kbId = useKbId();
  const toast = useToast();
  const compare = useCompareMutation(kbId);
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [resultView, setResultView] = useState<string>("audit");
  const [availability, setAvailability] = useState<string>("allow_all");
  const [result, setResult] = useState<SearchLabCompareResponse | null>(null);
  const [logId, setLogId] = useState<number | null>(null);

  async function run(event: FormEvent) {
    event.preventDefault();
    if (!query.trim() || compare.isPending) return;
    try {
      setResult(await compare.mutateAsync({ query: query.trim(), top_k: topK, result_view: resultView, availability_mode: availability }));
    } catch (cause) {
      toast.error(messageFor(cause, "检索失败"));
    }
  }

  const totalHits = result ? SEARCH_MODES.reduce((sum, mode) => sum + (result[mode.key]?.hits?.length ?? 0), 0) : 0;

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Search lab</p>
          <h1>检索台</h1>
          <p className="muted">以消费方视角验证：查询 → 命中知识 / Evidence → 引用与 provenance；三种模式并排对比。</p>
        </div>
      </header>

      <section className="panel">
        <form className="search-form" onSubmit={run} aria-label="检索">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入问题，例如：读凭证和写凭证分别用于什么场景？" aria-label="查询" />
          <label className="field">
            <span>top_k</span>
            <input type="number" min={1} max={50} value={topK} onChange={(event) => setTopK(Math.max(1, Number(event.target.value) || 1))} aria-label="top_k" />
          </label>
          <label className="field">
            <span>结果视图</span>
            <select value={resultView} onChange={(event) => setResultView(event.target.value)} aria-label="结果视图">
              {RESULT_VIEWS.map((view) => (
                <option key={view} value={view}>
                  {view}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>可用性</span>
            <select value={availability} onChange={(event) => setAvailability(event.target.value)} aria-label="可用性">
              {AVAILABILITY_MODES.map((mode) => (
                <option key={mode.value} value={mode.value}>
                  {mode.label}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className="primary-button" disabled={!query.trim() || compare.isPending}>
            {compare.isPending ? "检索中…" : "运行对比"}
          </button>
        </form>
        {result ? (
          <div className="actions" style={{ marginTop: 12, flexWrap: "wrap" }}>
            <span className="muted">发布面</span>
            {result.current_release ? (
              <Badge status={result.current_release.status}>
                {result.current_release.version}
              </Badge>
            ) : (
              <Badge tone="warning">workspace-only（未发布）</Badge>
            )}
            {result.retrieval_log_id ? (
              <button type="button" className="text-link as-button" onClick={() => setLogId(result.retrieval_log_id ?? null)}>
                检索日志 #{result.retrieval_log_id}
              </button>
            ) : null}
            <span className="muted">共 {totalHits} 条命中</span>
          </div>
        ) : null}
      </section>

      {result && totalHits === 0 ? (
        <section className="panel">
          <EmptyState
            title="没有命中"
            description={
              result.current_release
                ? "三种模式都没有结果。检查是否已导入文档并构建 Evidence；若知识项已确认但未发布，正式模式不会命中。"
                : "该知识库还没有发布版本：正式模式只检索已发布知识项。可以先确认 Evidence 命中，再发布第一个版本。"
            }
            action={
              <div className="actions">
                <Link className="outline-button" to={`/kbs/${kbId}/assets`}>
                  去导入
                </Link>
                <Link className="outline-button" to={`/kbs/${kbId}/production`}>
                  去构建 Evidence
                </Link>
                <Link className="primary-button" to={`/kbs/${kbId}/release`}>
                  去发布
                </Link>
              </div>
            }
          />
        </section>
      ) : null}

      {result && totalHits > 0 ? (
        <div className="search-grid">
          {SEARCH_MODES.map((mode) => (
            <ModeColumn key={mode.key} kbId={kbId} query={result.query} label={mode.label} description={mode.description} response={result[mode.key]} />
          ))}
        </div>
      ) : null}

      <div className="two-column">
        <RetrievalLogsPanel kbId={kbId} onOpen={setLogId} />
        <SourceGovernancePanel kbId={kbId} />
      </div>
      <LogDrawer kbId={kbId} logId={logId} onClose={() => setLogId(null)} />
    </>
  );
}

function ModeColumn({ kbId, query, label, description, response }: { kbId: number; query: string; label: string; description: string; response: ServiceSearchResponse }) {
  const hits = response?.hits ?? [];
  return (
    <section className="panel mode-column">
      <div className="panel-heading">
        <h2>{label}</h2>
        <span className="muted">{hits.length} 条</span>
      </div>
      <p className="muted">{description}</p>
      {hits.length ? hits.map((hit, index) => <HitCard key={`${hit.result_kind}-${hit.knowledge_item_id ?? ""}-${hit.evidence_id ?? ""}-${index}`} hit={hit} kbId={kbId} query={query} />) : <p className="muted state-row">无结果</p>}
    </section>
  );
}

function RetrievalLogsPanel({ kbId, onOpen }: { kbId: number; onOpen: (logId: number) => void }) {
  const logs = useRetrievalLogsQuery(kbId, 30);
  return (
    <section className="panel">
      <h2>检索日志</h2>
      <p className="muted">每次 /service/search 与检索台对比都会留痕，含混合检索 / rerank 的生效与降级标记。</p>
      {logs.isLoading ? <LoadingState /> : null}
      {logs.isError ? <ErrorState error={logs.error} fallback="加载检索日志失败" onRetry={() => void logs.refetch()} /> : null}
      {logs.data ? (
        <DataTable
          dense
          rows={logs.data}
          rowKey={(log) => log.id}
          onRowClick={(log) => onOpen(log.id)}
          empty={<EmptyState title="还没有检索日志" description="运行一次对比后，日志会出现在这里。" />}
          columns={[
            { key: "at", header: "时间", width: "150px", render: (log) => formatDateTime(log.created_at) },
            { key: "query", header: "查询", render: (log) => <span className="ellipsis" title={log.query}>{log.query}</span> },
            { key: "mode", header: "模式", width: "140px", render: (log) => <span className="mono">{log.query_mode}</span> },
            {
              key: "signals",
              header: "信号",
              width: "150px",
              render: (log) => {
                const signals = collectSignals(log.trace_json);
                const worst = signals.find((signal) => signal.value.startsWith("degraded")) ?? signals.find((signal) => signal.value !== "active") ?? signals[0];
                return worst ? <Badge tone={signalTone(worst.value)}>{worst.value.startsWith("degraded") ? "降级" : worst.value === "active" ? "混合生效" : worst.value}</Badge> : <span className="muted">—</span>;
              },
            },
          ]}
        />
      ) : null}
    </section>
  );
}

function SourceGovernancePanel({ kbId }: { kbId: number }) {
  const governance = useSourceGovernanceQuery(kbId);
  const counts = governance.data?.status_counts ?? {};
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>来源健康</h2>
        <Link className="text-link" to={`/kbs/${kbId}/assets?tab=sources`}>
          资产与导入 →
        </Link>
      </div>
      <p className="muted">缺失或变更的资产会影响引用可信度；检索可按「可用性」过滤这些来源。</p>
      {governance.isLoading ? <LoadingState /> : null}
      {governance.isError ? <ErrorState error={governance.error} fallback="加载来源健康失败" onRetry={() => void governance.refetch()} /> : null}
      {governance.data ? (
        <>
          <div className="chip-row">
            {Object.entries(counts).map(([status, count]) => (
              <span key={status}>
                <Badge status={status} /> {String(count)}
              </span>
            ))}
            {!Object.keys(counts).length ? <span>暂无统计</span> : null}
          </div>
          <DataTable
            dense
            rows={(governance.data.assets ?? []).filter((asset) => asset.availability_status !== "available")}
            rowKey={(asset) => asset.asset_id}
            empty={<p className="muted state-row">所有资产可用，没有需要处理的来源问题。</p>}
            columns={[
              { key: "path", header: "资产", render: (asset) => <span className="mono ellipsis" title={asset.asset_path}>{asset.asset_path}</span> },
              { key: "status", header: "可用性", width: "110px", render: (asset) => <Badge status={asset.availability_status} /> },
              { key: "evidence", header: "Evidence", width: "80px", align: "right", render: (asset) => asset.evidence_count ?? 0 },
            ]}
          />
        </>
      ) : null}
    </section>
  );
}

function LogDrawer({ kbId, logId, onClose }: { kbId: number; logId: number | null; onClose: () => void }) {
  const log = useRetrievalLogQuery(kbId, logId);
  return (
    <Drawer open={logId !== null} title={`检索日志 #${logId ?? ""}`} onClose={onClose} width={720}>
      {log.isLoading ? <LoadingState /> : null}
      {log.isError ? <ErrorState error={log.error} fallback="加载日志失败" /> : null}
      {log.data ? (
        <>
          <dl className="detail-grid">
            <div>
              <dt>查询</dt>
              <dd>{log.data.query}</dd>
            </div>
            <div>
              <dt>模式 / 发布</dt>
              <dd>
                <span className="mono">{log.data.query_mode}</span> · {log.data.release_id ? `release #${log.data.release_id}` : "workspace"}
              </dd>
            </div>
            <div>
              <dt>时间</dt>
              <dd>{formatDateTime(log.data.created_at)}</dd>
            </div>
            <div>
              <dt>调用方</dt>
              <dd>{log.data.service_principal_id ? `principal #${log.data.service_principal_id} · grant #${log.data.service_grant_id}` : "控制台"}</dd>
            </div>
          </dl>
          <h3 style={{ margin: "14px 0 6px" }}>检索信号</h3>
          <TraceView trace={log.data.trace_json} />
          <h3 style={{ margin: "14px 0 6px" }}>结果摘要</h3>
          <pre className="pre-json">{JSON.stringify(log.data.result_summary_json ?? {}, null, 2)}</pre>
        </>
      ) : null}
    </Drawer>
  );
}
