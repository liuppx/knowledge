import { FormEvent, useState } from "react";

import { messageFor } from "../../api/client";
import { SOURCE_TYPES, type Source } from "../../api/endpoints/sources";
import { useCreateSourceMutation, useScanSourceMutation, useSourceAssetsQuery, useSourcesQuery, useUpdateSourceMutation } from "../../api/queries/sources";
import { Badge, DataTable, Drawer, EmptyState, ErrorState, LoadingState, formatDateTime, formatRelative, useToast } from "../../ui";

export function SourcesPanel({ kbId }: { kbId: number }) {
  const toast = useToast();
  const sources = useSourcesQuery(kbId);
  const create = useCreateSourceMutation(kbId);
  const update = useUpdateSourceMutation(kbId);
  const scan = useScanSourceMutation(kbId);
  const [type, setType] = useState<string>("warehouse");
  const [path, setPath] = useState("");
  const [scope, setScope] = useState("directory");
  const [assetsFor, setAssetsFor] = useState<Source | null>(null);
  const assets = useSourceAssetsQuery(kbId, assetsFor?.id ?? null);
  const placeholder = SOURCE_TYPES.find((item) => item.value === type)?.placeholder ?? "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!path.trim() || create.isPending) return;
    try {
      await create.mutateAsync({ source_type: type, source_path: path.trim(), scope_type: scope, enabled: true, missing_policy: "mark_missing" });
      setPath("");
      toast.success("来源已添加，可先扫描查看资产");
    } catch (cause) {
      toast.error(messageFor(cause, "添加来源失败"));
    }
  }

  async function runScan(source: Source) {
    try {
      const result = await scan.mutateAsync(source.id);
      const stats = result.stats;
      toast.success(`扫描完成：${stats.total_assets} 个资产（可用 ${stats.available_assets}，变更 ${stats.changed_assets}，缺失 ${stats.missing_assets}）`);
    } catch (cause) {
      toast.error(messageFor(cause, "扫描失败"));
    }
  }

  return (
    <section className="panel">
      <h2>来源</h2>
      <p className="muted">来源是知识生产的输入：扫描后得到资产清单，再在「知识生产」中按来源或资产构建 Evidence。</p>
      <form className="form-row" onSubmit={submit} aria-label="添加来源">
        <select value={type} onChange={(event) => setType(event.target.value)} aria-label="来源类型">
          {SOURCE_TYPES.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <input value={path} onChange={(event) => setPath(event.target.value)} placeholder={placeholder} aria-label="来源路径" />
        <div className="actions">
          <select value={scope} onChange={(event) => setScope(event.target.value)} aria-label="范围">
            <option value="directory">目录</option>
            <option value="file">单文件</option>
          </select>
          <button type="submit" className="primary-button" disabled={!path.trim() || create.isPending}>
            添加
          </button>
        </div>
      </form>
      {sources.isLoading ? <LoadingState /> : null}
      {sources.isError ? <ErrorState error={sources.error} fallback="加载来源失败" onRetry={() => void sources.refetch()} /> : null}
      {sources.data ? (
        <DataTable
          rows={sources.data}
          rowKey={(source) => source.id}
          empty={<EmptyState title="还没有来源" description="添加 Warehouse 目录、本地目录或 GitHub 仓库作为来源，然后扫描资产。" />}
          columns={[
            {
              key: "path",
              header: "路径",
              render: (source) => (
                <div>
                  <span className="mono ellipsis">{source.source_path}</span>
                  <span className="muted">
                    {source.source_type} · {source.scope_type} · 缺失策略 {source.missing_policy}
                  </span>
                </div>
              ),
            },
            {
              key: "enabled",
              header: "启用",
              width: "70px",
              render: (source) => (
                <input
                  type="checkbox"
                  checked={source.enabled}
                  aria-label={`启用来源 ${source.source_path}`}
                  onChange={(event) => void update.mutateAsync({ sourceId: source.id, payload: { enabled: event.target.checked } }).catch((cause) => toast.error(messageFor(cause, "更新失败")))}
                />
              ),
            },
            { key: "sync", header: "同步", width: "110px", render: (source) => <Badge status={source.sync_status} /> },
            { key: "synced", header: "最近同步", width: "120px", render: (source) => formatRelative(source.last_synced_at) },
            {
              key: "actions",
              header: "",
              width: "160px",
              align: "right",
              render: (source) => (
                <div className="actions">
                  <button type="button" className="outline-button" onClick={() => void runScan(source)} disabled={scan.isPending}>
                    扫描
                  </button>
                  <button type="button" className="outline-button" onClick={() => setAssetsFor(source)}>
                    资产
                  </button>
                </div>
              ),
            },
          ]}
        />
      ) : null}
      <Drawer open={assetsFor !== null} title={`资产 · ${assetsFor?.source_path ?? ""}`} onClose={() => setAssetsFor(null)} width={720}>
        {assets.isLoading ? <LoadingState /> : null}
        {assets.isError ? <ErrorState error={assets.error} fallback="加载资产失败" /> : null}
        {assets.data ? (
          <DataTable
            dense
            rows={assets.data}
            rowKey={(asset) => asset.id}
            empty={<EmptyState title="没有资产" description="先执行一次扫描。" />}
            columns={[
              { key: "name", header: "资产", render: (asset) => <span className="ellipsis" title={asset.asset_path}>{asset.asset_name}</span> },
              { key: "type", header: "类型", width: "90px", render: (asset) => asset.asset_type },
              { key: "status", header: "可用性", width: "110px", render: (asset) => <Badge status={asset.availability_status} /> },
              { key: "ingested", header: "最近摄取", width: "170px", render: (asset) => formatDateTime(asset.last_ingested_at) },
            ]}
          />
        ) : null}
      </Drawer>
    </section>
  );
}
