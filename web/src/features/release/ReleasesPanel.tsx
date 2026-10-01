import { FormEvent, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { messageFor } from "../../api/client";
import type { Release } from "../../api/endpoints/releases";
import { useItemsQuery } from "../../api/queries/production";
import { useCurrentReleaseQuery, useHotfixReleaseMutation, usePublishReleaseMutation, useReleaseQuery, useReleasesQuery, useRollbackReleaseMutation } from "../../api/queries/releases";
import { Badge, DataTable, Drawer, EmptyState, ErrorState, LoadingState, formatDateTime, shortenMiddle, useToast } from "../../ui";
import { diffReleases } from "./diff";

type Dialog = { kind: "publish" } | { kind: "detail"; release: Release } | { kind: "hotfix"; release: Release } | { kind: "rollback"; release: Release } | { kind: "diff"; from: Release; to: Release } | null;

function suggestVersion(): string {
  const now = new Date();
  return `${now.getFullYear()}.${String(now.getMonth() + 1).padStart(2, "0")}.${String(now.getDate()).padStart(2, "0")}`;
}

export function ReleasesPanel({ kbId }: { kbId: number }) {
  const toast = useToast();
  const releases = useReleasesQuery(kbId);
  const current = useCurrentReleaseQuery(kbId);
  const publish = usePublishReleaseMutation(kbId);
  const hotfix = useHotfixReleaseMutation(kbId);
  const rollback = useRollbackReleaseMutation(kbId);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [diffFrom, setDiffFrom] = useState<number | "">("");
  const rows = useMemo(() => [...(releases.data ?? [])].sort((a, b) => b.id - a.id), [releases.data]);
  const currentId = current.data?.release?.id ?? null;

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>发布版本</h2>
        <button type="button" className="primary-button" onClick={() => setDialog({ kind: "publish" })}>
          发布新版本
        </button>
      </div>
      <p className="muted">发布把当前已确认的知识项固化为消费方可检索的版本；热修在某版本基础上替换指定知识项；回滚会基于旧版本生成新版本。</p>
      {releases.isLoading ? <LoadingState /> : null}
      {releases.isError ? <ErrorState error={releases.error} fallback="加载发布版本失败" onRetry={() => void releases.refetch()} /> : null}
      {releases.data ? (
        <DataTable
          rows={rows}
          rowKey={(release) => release.id}
          selectedKey={currentId}
          onRowClick={(release) => setDialog({ kind: "detail", release })}
          empty={
            <EmptyState
              title="还没有发布版本"
              description="消费方只能检索已发布版本。先在「知识生产」确认知识项，再发布第一个版本。"
              action={
                <div className="actions">
                  <Link className="outline-button" to={`/kbs/${kbId}/production?tab=items`}>
                    查看知识项
                  </Link>
                  <button type="button" className="primary-button" onClick={() => setDialog({ kind: "publish" })}>
                    发布新版本
                  </button>
                </div>
              }
            />
          }
          columns={[
            {
              key: "version",
              header: "版本",
              render: (release) => (
                <span>
                  <strong>{release.version}</strong> {release.id === currentId ? <Badge tone="success">当前</Badge> : null}
                </span>
              ),
            },
            { key: "status", header: "状态", width: "110px", render: (release) => <Badge status={release.status} /> },
            { key: "published", header: "发布时间", width: "170px", render: (release) => formatDateTime(release.published_at) },
            { key: "by", header: "发布者", width: "130px", render: (release) => <span className="mono">{shortenMiddle(release.created_by)}</span> },
            { key: "supersedes", header: "取代", width: "80px", align: "right", render: (release) => (release.supersedes_release_id ? `#${release.supersedes_release_id}` : "—") },
            { key: "note", header: "说明", render: (release) => <span className="muted ellipsis">{release.release_note || "—"}</span> },
            {
              key: "actions",
              header: "",
              width: "230px",
              align: "right",
              render: (release) => (
                <div className="actions" onClick={(event) => event.stopPropagation()}>
                  <button type="button" className="outline-button" onClick={() => setDialog({ kind: "hotfix", release })}>
                    热修
                  </button>
                  <button type="button" className="outline-button" onClick={() => setDialog({ kind: "rollback", release })} disabled={release.id === currentId} aria-label={`回滚到 ${release.version}`}>
                    回滚到此
                  </button>
                  <select
                    aria-label={`对比 ${release.version}`}
                    value={diffFrom}
                    onChange={(event) => {
                      const fromId = Number(event.target.value);
                      const from = rows.find((item) => item.id === fromId);
                      setDiffFrom("");
                      if (from) setDialog({ kind: "diff", from, to: release });
                    }}
                  >
                    <option value="">对比…</option>
                    {rows.filter((item) => item.id !== release.id).map((item) => (
                      <option key={item.id} value={item.id}>
                        与 {item.version}
                      </option>
                    ))}
                  </select>
                </div>
              ),
            },
          ]}
        />
      ) : null}

      <Drawer open={dialog?.kind === "publish"} title="发布新版本" onClose={() => setDialog(null)}>
        <ReleaseForm
          submitLabel="发布"
          busy={publish.isPending}
          onCancel={() => setDialog(null)}
          onSubmit={async (values) => {
            try {
              const detail = await publish.mutateAsync(values);
              toast.success(`已发布 ${detail.release.version}（${detail.items?.length ?? 0} 个知识项）`);
              setDialog(null);
            } catch (cause) {
              toast.error(messageFor(cause, "发布失败"));
            }
          }}
        />
      </Drawer>
      <ReleaseDetailDrawer kbId={kbId} release={dialog?.kind === "detail" ? dialog.release : null} onClose={() => setDialog(null)} />
      <Drawer open={dialog?.kind === "hotfix"} title={dialog?.kind === "hotfix" ? `基于 ${dialog.release.version} 热修` : ""} onClose={() => setDialog(null)} width={680}>
        {dialog?.kind === "hotfix" ? (
          <HotfixForm
            kbId={kbId}
            baseVersion={dialog.release.version}
            busy={hotfix.isPending}
            onCancel={() => setDialog(null)}
            onSubmit={async (values) => {
              try {
                const detail = await hotfix.mutateAsync({ releaseId: dialog.release.id, payload: { ...values, base_release_id: dialog.release.id } });
                toast.success(`热修版本 ${detail.release.version} 已发布`);
                setDialog(null);
              } catch (cause) {
                toast.error(messageFor(cause, "热修失败"));
              }
            }}
          />
        ) : null}
      </Drawer>
      <Drawer open={dialog?.kind === "rollback"} title={dialog?.kind === "rollback" ? `回滚到 ${dialog.release.version}` : ""} onClose={() => setDialog(null)}>
        {dialog?.kind === "rollback" ? (
          <>
            <p className="alert" role="note">
              回滚会以 {dialog.release.version} 的内容生成一个新版本并立即生效，当前版本被取代；消费方下一次检索即切换。
            </p>
            <ReleaseForm
              submitLabel="确认回滚"
              danger
              busy={rollback.isPending}
              defaultNote={`回滚到 ${dialog.release.version}`}
              onCancel={() => setDialog(null)}
              onSubmit={async (values) => {
                try {
                  const detail = await rollback.mutateAsync({ releaseId: dialog.release.id, payload: values });
                  toast.success(`已回滚，新版本 ${detail.release.version}`);
                  setDialog(null);
                } catch (cause) {
                  toast.error(messageFor(cause, "回滚失败"));
                }
              }}
            />
          </>
        ) : null}
      </Drawer>
      <DiffDrawer kbId={kbId} pair={dialog?.kind === "diff" ? { from: dialog.from, to: dialog.to } : null} onClose={() => setDialog(null)} />
    </section>
  );
}

function ReleaseForm({ submitLabel, busy, danger, defaultNote = "", onSubmit, onCancel }: { submitLabel: string; busy: boolean; danger?: boolean; defaultNote?: string; onSubmit: (values: { version: string; release_note: string }) => Promise<void>; onCancel: () => void }) {
  const [version, setVersion] = useState(suggestVersion());
  const [note, setNote] = useState(defaultNote);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!version.trim() || busy) return;
    void onSubmit({ version: version.trim(), release_note: note.trim() });
  }
  return (
    <form className="form-grid" onSubmit={submit} aria-label="发布表单">
      <label className="field">
        <span>版本号</span>
        <input value={version} onChange={(event) => setVersion(event.target.value)} required className="mono" />
      </label>
      <label className="field">
        <span>发布说明</span>
        <textarea value={note} onChange={(event) => setNote(event.target.value)} rows={3} placeholder="这个版本变更了什么" />
      </label>
      <div className="modal-actions">
        <button type="button" className="outline-button" onClick={onCancel} disabled={busy}>
          取消
        </button>
        <button type="submit" className={danger ? "danger-button" : "primary-button"} disabled={busy || !version.trim()}>
          {busy ? "处理中…" : submitLabel}
        </button>
      </div>
    </form>
  );
}

function HotfixForm({ kbId, baseVersion, busy, onSubmit, onCancel }: { kbId: number; baseVersion: string; busy: boolean; onSubmit: (values: { version: string; release_note: string; knowledge_item_ids: number[] }) => Promise<void>; onCancel: () => void }) {
  const items = useItemsQuery(kbId);
  const [version, setVersion] = useState(`${baseVersion}-hotfix.1`);
  const [note, setNote] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  function toggle(id: number) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!version.trim() || !selected.size || busy) return;
    void onSubmit({ version: version.trim(), release_note: note.trim(), knowledge_item_ids: [...selected] });
  }
  return (
    <form className="form-grid" onSubmit={submit} aria-label="热修表单">
      <label className="field">
        <span>版本号</span>
        <input value={version} onChange={(event) => setVersion(event.target.value)} required className="mono" />
      </label>
      <label className="field">
        <span>说明</span>
        <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="修了什么" />
      </label>
      <div className="field">
        <span>要热修进版本的知识项（使用其当前修订）</span>
        {items.isLoading ? <LoadingState /> : null}
        <ul className="check-list">
          {(items.data ?? []).map((item) => (
            <li key={item.id}>
              <label>
                <input type="checkbox" checked={selected.has(item.id)} onChange={() => toggle(item.id)} />
                <span>
                  #{item.id} {item.title ?? "（无修订）"} <span className="muted">· 修订 {item.revision_no ?? "—"}</span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      </div>
      <div className="modal-actions">
        <button type="button" className="outline-button" onClick={onCancel} disabled={busy}>
          取消
        </button>
        <button type="submit" className="primary-button" disabled={busy || !version.trim() || !selected.size}>
          {busy ? "发布中…" : `发布热修（${selected.size}）`}
        </button>
      </div>
    </form>
  );
}

function ReleaseDetailDrawer({ kbId, release, onClose }: { kbId: number; release: Release | null; onClose: () => void }) {
  const detail = useReleaseQuery(kbId, release?.id ?? null);
  return (
    <Drawer open={release !== null} title={release ? `版本 ${release.version}` : ""} onClose={onClose} width={720}>
      {release ? (
        <>
          <div className="actions" style={{ marginBottom: 10 }}>
            <Badge status={release.status} />
            <span className="muted">
              {formatDateTime(release.published_at)} · {shortenMiddle(release.created_by)}
            </span>
          </div>
          {release.release_note ? <p>{release.release_note}</p> : null}
          {detail.isLoading ? <LoadingState /> : null}
          {detail.isError ? <ErrorState error={detail.error} fallback="加载版本明细失败" /> : null}
          {detail.data ? (
            <DataTable
              dense
              rows={detail.data.items ?? []}
              rowKey={(item) => item.id}
              empty={<p className="muted state-row">该版本不包含知识项。</p>}
              columns={[
                { key: "item", header: "知识项", render: (item) => <Link to={`/kbs/${kbId}/production?item=${item.knowledge_item_id}`}>#{item.knowledge_item_id}</Link> },
                { key: "rev", header: "修订", width: "90px", render: (item) => `#${item.knowledge_item_revision_id}` },
                { key: "hash", header: "版本哈希", width: "140px", render: (item) => <span className="mono">{shortenMiddle(item.item_version_hash, 5)}</span> },
                { key: "health", header: "内容健康", width: "110px", render: (item) => <Badge status={item.content_health_status} /> },
              ]}
            />
          ) : null}
        </>
      ) : null}
    </Drawer>
  );
}

function DiffDrawer({ kbId, pair, onClose }: { kbId: number; pair: { from: Release; to: Release } | null; onClose: () => void }) {
  const from = useReleaseQuery(kbId, pair?.from.id ?? null);
  const to = useReleaseQuery(kbId, pair?.to.id ?? null);
  const diff = from.data && to.data ? diffReleases(from.data.items ?? [], to.data.items ?? []) : null;
  return (
    <Drawer open={pair !== null} title={pair ? `${pair.from.version} → ${pair.to.version}` : ""} onClose={onClose} width={720}>
      {from.isLoading || to.isLoading ? <LoadingState /> : null}
      {diff ? (
        <>
          <div className="chip-row">
            <span>新增 {diff.added.length}</span>
            <span>移除 {diff.removed.length}</span>
            <span>变更 {diff.changed.length}</span>
            <span>未变 {diff.unchanged}</span>
          </div>
          <ul className="diff-list" aria-label="版本差异">
            {diff.added.map((item) => (
              <li key={`a-${item.knowledge_item_id}`} className="diff-added">
                <Badge tone="success">新增</Badge> <Link to={`/kbs/${kbId}/production?item=${item.knowledge_item_id}`}>知识项 #{item.knowledge_item_id}</Link> <span className="muted">修订 #{item.knowledge_item_revision_id}</span>
              </li>
            ))}
            {diff.changed.map(({ before, after }) => (
              <li key={`c-${after.knowledge_item_id}`} className="diff-changed">
                <Badge tone="warning">变更</Badge> <Link to={`/kbs/${kbId}/production?item=${after.knowledge_item_id}`}>知识项 #{after.knowledge_item_id}</Link> <span className="muted">修订 #{before.knowledge_item_revision_id} → #{after.knowledge_item_revision_id}</span>
              </li>
            ))}
            {diff.removed.map((item) => (
              <li key={`r-${item.knowledge_item_id}`} className="diff-removed">
                <Badge tone="danger">移除</Badge> <Link to={`/kbs/${kbId}/production?item=${item.knowledge_item_id}`}>知识项 #{item.knowledge_item_id}</Link> <span className="muted">修订 #{item.knowledge_item_revision_id}</span>
              </li>
            ))}
            {!diff.added.length && !diff.changed.length && !diff.removed.length ? <li className="muted">两个版本的知识项完全一致。</li> : null}
          </ul>
        </>
      ) : null}
    </Drawer>
  );
}
