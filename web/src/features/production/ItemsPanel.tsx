import { useMemo, useState } from "react";

import { messageFor } from "../../api/client";
import { ITEM_TYPES, ITEM_TYPE_LABELS, LIFECYCLE_STATUSES, type KnowledgeItemRevision } from "../../api/endpoints/production";
import { useCreateManualItemMutation, useItemQuery, useItemsQuery, useUpdateItemMutation } from "../../api/queries/production";
import { Badge, DataTable, Drawer, EmptyState, ErrorState, LoadingState, formatDateTime, useToast } from "../../ui";
import { excerpt } from "./EvidencePanel";
import { ItemForm } from "./ItemForm";

type Props = { kbId: number; selectedItemId: number | null; onSelectItem: (id: number | null) => void; onOpenEvidence: (evidenceId: number) => void };

export function ItemsPanel({ kbId, selectedItemId, onSelectItem, onOpenEvidence }: Props) {
  const toast = useToast();
  const items = useItemsQuery(kbId);
  const create = useCreateManualItemMutation(kbId);
  const [itemType, setItemType] = useState("");
  const [lifecycle, setLifecycle] = useState("");
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (items.data ?? []).filter(
      (item) =>
        (!itemType || item.item_type === itemType) &&
        (!lifecycle || item.lifecycle_status === lifecycle) &&
        (!needle || `${item.title ?? ""} ${item.statement ?? ""}`.toLowerCase().includes(needle)),
    );
  }, [items.data, itemType, lifecycle, search]);

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>知识项</h2>
        <button type="button" className="primary-button" onClick={() => setCreating(true)}>
          手工新建
        </button>
      </div>
      <p className="muted">正式知识项带修订历史与 Evidence 关联；发布版本只包含这里已确认的知识项。</p>
      <div className="toolbar">
        <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="按标题 / 陈述搜索" aria-label="搜索知识项" />
        <select aria-label="类型" value={itemType} onChange={(event) => setItemType(event.target.value)}>
          <option value="">全部类型</option>
          {ITEM_TYPES.map((value) => (
            <option key={value} value={value}>
              {ITEM_TYPE_LABELS[value]}
            </option>
          ))}
        </select>
        <select aria-label="生命周期" value={lifecycle} onChange={(event) => setLifecycle(event.target.value)}>
          <option value="">全部生命周期</option>
          {LIFECYCLE_STATUSES.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </div>
      {items.isLoading ? <LoadingState /> : null}
      {items.isError ? <ErrorState error={items.error} fallback="加载知识项失败" onRetry={() => void items.refetch()} /> : null}
      {items.data ? (
        <DataTable
          rows={rows}
          rowKey={(item) => item.id}
          selectedKey={selectedItemId}
          onRowClick={(item) => onSelectItem(item.id)}
          empty={
            <EmptyState
              title={items.data.length ? "没有匹配的知识项" : "还没有正式知识项"}
              description={items.data.length ? "调整筛选条件。" : "在「候选审核」接受候选，或手工新建一条知识项。"}
              action={
                items.data.length ? null : (
                  <button type="button" className="primary-button" onClick={() => setCreating(true)}>
                    手工新建
                  </button>
                )
              }
            />
          }
          columns={[
            { key: "id", header: "#", width: "70px", render: (item) => item.id },
            {
              key: "title",
              header: "知识项",
              render: (item) => (
                <div>
                  <strong>{item.title ?? "（无当前修订）"}</strong>
                  <span className="muted">{excerpt(item.statement ?? "", 110)}</span>
                </div>
              ),
            },
            { key: "type", header: "类型", width: "90px", render: (item) => ITEM_TYPE_LABELS[item.item_type] ?? item.item_type },
            { key: "origin", header: "来源", width: "110px", render: (item) => item.origin_type },
            { key: "lifecycle", header: "生命周期", width: "100px", render: (item) => <Badge status={item.lifecycle_status} /> },
            { key: "review", header: "修订审核", width: "110px", render: (item) => <Badge status={item.review_status ?? null} /> },
            { key: "rev", header: "修订", width: "60px", align: "right", render: (item) => item.revision_no ?? "—" },
            { key: "evidence", header: "Evidence", width: "80px", align: "right", render: (item) => item.evidence_count ?? 0 },
            { key: "updated", header: "更新", width: "160px", render: (item) => formatDateTime(item.updated_at) },
          ]}
        />
      ) : null}
      <Drawer open={creating} title="手工新建知识项" onClose={() => setCreating(false)} width={680}>
        <ItemForm
          submitLabel="创建"
          busy={create.isPending}
          onCancel={() => setCreating(false)}
          onSubmit={async (values) => {
            try {
              const detail = await create.mutateAsync({ ...values, item_contract_version: "v1", structured_payload_json: {}, applicability_scope_json: {} });
              toast.success(`知识项 #${detail.item.id} 已创建`);
              setCreating(false);
              onSelectItem(detail.item.id);
            } catch (cause) {
              toast.error(messageFor(cause, "创建失败"));
            }
          }}
        />
      </Drawer>
      <ItemDetailDrawer kbId={kbId} itemId={selectedItemId} onClose={() => onSelectItem(null)} onOpenEvidence={onOpenEvidence} />
    </section>
  );
}

function ItemDetailDrawer({ kbId, itemId, onClose, onOpenEvidence }: { kbId: number; itemId: number | null; onClose: () => void; onOpenEvidence: (evidenceId: number) => void }) {
  const toast = useToast();
  const detail = useItemQuery(kbId, itemId);
  const update = useUpdateItemMutation(kbId);
  const [editing, setEditing] = useState(false);
  const revision = detail.data?.current_revision ?? null;

  return (
    <Drawer open={itemId !== null} title={revision?.title ?? `知识项 #${itemId ?? ""}`} onClose={onClose} width={760}>
      {detail.isLoading ? <LoadingState /> : null}
      {detail.isError ? <ErrorState error={detail.error} fallback="加载知识项失败" /> : null}
      {detail.data ? (
        <>
          <div className="actions" style={{ marginBottom: 12, flexWrap: "wrap" }}>
            <Badge status={detail.data.item.lifecycle_status} />
            {revision ? <Badge status={revision.review_status} /> : null}
            {revision ? <Badge status={revision.visibility_status} /> : null}
            {detail.data.item.is_hotfix ? <Badge status="hotfix" /> : null}
            <span className="muted">
              {ITEM_TYPE_LABELS[detail.data.item.item_type] ?? detail.data.item.item_type} · {detail.data.item.origin_type}
            </span>
            <button type="button" className="outline-button" style={{ marginLeft: "auto" }} onClick={() => setEditing((value) => !value)} disabled={!revision}>
              {editing ? "取消编辑" : "编辑（新修订）"}
            </button>
          </div>
          {editing && revision ? (
            <ItemForm
              key={revision.id}
              initial={{ title: revision.title, statement: revision.statement, item_type: detail.data.item.item_type, evidence_unit_ids: (revision.evidence_links ?? []).map((link) => link.evidence_unit_id), source_note: "" }}
              submitLabel="保存为新修订"
              busy={update.isPending}
              onCancel={() => setEditing(false)}
              onSubmit={async (values) => {
                try {
                  await update.mutateAsync({ itemId: detail.data!.item.id, payload: values });
                  toast.success("已保存为新修订");
                  setEditing(false);
                } catch (cause) {
                  toast.error(messageFor(cause, "保存失败"));
                }
              }}
            />
          ) : revision ? (
            <RevisionView revision={revision} onOpenEvidence={onOpenEvidence} />
          ) : (
            <p className="muted">该知识项还没有修订。</p>
          )}
          <h3 style={{ margin: "18px 0 8px" }}>修订历史（{detail.data.revisions?.length ?? 0}）</h3>
          <DataTable
            dense
            rows={detail.data.revisions ?? []}
            rowKey={(item) => item.id}
            empty={<p className="muted state-row">暂无修订。</p>}
            columns={[
              { key: "no", header: "修订", width: "60px", render: (item) => `#${item.revision_no}` },
              { key: "title", header: "标题", render: (item) => item.title },
              { key: "review", header: "审核", width: "100px", render: (item) => <Badge status={item.review_status} /> },
              { key: "visibility", header: "可见性", width: "90px", render: (item) => <Badge status={item.visibility_status} /> },
              { key: "by", header: "创建者", width: "120px", render: (item) => <span className="mono ellipsis">{item.created_by}</span> },
              { key: "at", header: "时间", width: "160px", render: (item) => formatDateTime(item.created_at) },
            ]}
          />
        </>
      ) : null}
    </Drawer>
  );
}

function RevisionView({ revision, onOpenEvidence }: { revision: KnowledgeItemRevision; onOpenEvidence: (evidenceId: number) => void }) {
  return (
    <>
      <p className="evidence-text">{revision.statement}</p>
      <dl className="detail-grid">
        <div>
          <dt>修订 / 契约</dt>
          <dd>
            #{revision.revision_no} · {revision.item_contract_version}
          </dd>
        </div>
        <div>
          <dt>来源类型</dt>
          <dd>{revision.provenance_type}</dd>
        </div>
        <div>
          <dt>创建者 / 审核者</dt>
          <dd className="mono">
            {revision.created_by || "—"} / {revision.reviewed_by || "—"}
          </dd>
        </div>
        <div>
          <dt>来源说明</dt>
          <dd>{revision.source_note || "—"}</dd>
        </div>
      </dl>
      {revision.structured_payload_json && Object.keys(revision.structured_payload_json).length ? <pre className="pre-json">{JSON.stringify(revision.structured_payload_json, null, 2)}</pre> : null}
      <h3 style={{ margin: "16px 0 8px" }}>Evidence 关联（{revision.evidence_links?.length ?? 0}）</h3>
      {(revision.evidence_links ?? []).length ? (
        <ul className="link-list">
          {(revision.evidence_links ?? []).map((link) => (
            <li key={link.id}>
              <button type="button" className="text-link" onClick={() => onOpenEvidence(link.evidence_unit_id)} aria-label={`查看 Evidence ${link.evidence_unit_id}`}>
                Evidence #{link.evidence_unit_id}
              </button>
              <span className="muted">
                {link.role} · rank {link.rank}
                {link.summary ? ` · ${link.summary}` : ""}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">没有关联 Evidence——没有证据链的知识项在检索中无法回查来源，建议编辑补充。</p>
      )}
    </>
  );
}
