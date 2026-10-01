import { FormEvent, useState } from "react";

import { messageFor } from "../../api/client";
import { CANDIDATE_REVIEW_STATUSES, ITEM_TYPES, ITEM_TYPE_LABELS, type Candidate } from "../../api/endpoints/production";
import { useAcceptCandidateMutation, useCandidatesQuery, useRejectCandidateMutation } from "../../api/queries/production";
import { Badge, ConfirmDialog, DataTable, Drawer, EmptyState, ErrorState, LoadingState, formatDateTime, useToast } from "../../ui";
import { excerpt } from "./EvidencePanel";

function evidenceIdsFrom(candidate: Candidate): number[] {
  const raw = (candidate.provenance_json as { evidence_unit_ids?: unknown } | undefined)?.evidence_unit_ids;
  return Array.isArray(raw) ? raw.map(Number).filter((id) => Number.isInteger(id) && id > 0) : [];
}

type Props = { kbId: number; onAccepted: (itemId: number) => void };

export function CandidatesPanel({ kbId, onAccepted }: Props) {
  const toast = useToast();
  const candidates = useCandidatesQuery(kbId);
  const accept = useAcceptCandidateMutation(kbId);
  const reject = useRejectCandidateMutation(kbId);
  const [status, setStatus] = useState<string>("pending_review");
  const [accepting, setAccepting] = useState<Candidate | null>(null);
  const [rejecting, setRejecting] = useState<Candidate | null>(null);
  const rows = (candidates.data ?? []).filter((candidate) => !status || candidate.review_status === status);

  async function confirmReject() {
    if (!rejecting) return;
    try {
      await reject.mutateAsync({ candidateId: rejecting.id, payload: { source_note: "" } });
      toast.success("候选已拒绝");
      setRejecting(null);
    } catch (cause) {
      toast.error(messageFor(cause, "拒绝失败"));
    }
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>候选审核</h2>
        <select aria-label="审核状态" value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="">全部状态</option>
          {CANDIDATE_REVIEW_STATUSES.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </div>
      <p className="muted">候选来自 Evidence 的自动抽取；接受后成为正式知识项（可在接受前修订标题与陈述），拒绝则保留记录。</p>
      {candidates.isLoading ? <LoadingState /> : null}
      {candidates.isError ? <ErrorState error={candidates.error} fallback="加载候选失败" onRetry={() => void candidates.refetch()} /> : null}
      {candidates.data ? (
        <DataTable
          rows={rows}
          rowKey={(candidate) => candidate.id}
          empty={<EmptyState title={status ? "没有该状态的候选" : "还没有候选"} description="在「Evidence」页选择来源或资产并点击「生成候选」。" />}
          columns={[
            {
              key: "title",
              header: "候选",
              render: (candidate) => (
                <div>
                  <strong>{candidate.title}</strong>
                  <span className="muted" title={candidate.statement}>
                    {excerpt(candidate.statement, 120)}
                  </span>
                </div>
              ),
            },
            { key: "type", header: "类型", width: "90px", render: (candidate) => ITEM_TYPE_LABELS[candidate.item_type] ?? candidate.item_type },
            { key: "confidence", header: "置信度", width: "80px", align: "right", render: (candidate) => (candidate.origin_confidence ?? null) !== null ? Number(candidate.origin_confidence).toFixed(2) : "—" },
            { key: "status", header: "状态", width: "100px", render: (candidate) => <Badge status={candidate.review_status} /> },
            { key: "created", header: "生成时间", width: "160px", render: (candidate) => formatDateTime(candidate.created_at) },
            {
              key: "actions",
              header: "",
              width: "150px",
              align: "right",
              render: (candidate) =>
                candidate.review_status === "pending_review" ? (
                  <div className="actions">
                    <button type="button" className="primary-button" onClick={() => setAccepting(candidate)} aria-label={`接受 ${candidate.title}`}>
                      接受
                    </button>
                    <button type="button" className="outline-button" onClick={() => setRejecting(candidate)} aria-label={`拒绝 ${candidate.title}`}>
                      拒绝
                    </button>
                  </div>
                ) : null,
            },
          ]}
        />
      ) : null}
      <Drawer open={accepting !== null} title="接受为正式知识项" onClose={() => setAccepting(null)} width={640}>
        {accepting ? (
          <AcceptForm
            key={accepting.id}
            candidate={accepting}
            busy={accept.isPending}
            onCancel={() => setAccepting(null)}
            onSubmit={async (payload) => {
              try {
                const detail = await accept.mutateAsync({ candidateId: accepting.id, payload });
                toast.success(`已接受为知识项 #${detail.item.id}`);
                setAccepting(null);
                onAccepted(detail.item.id);
              } catch (cause) {
                toast.error(messageFor(cause, "接受失败"));
              }
            }}
          />
        ) : null}
      </Drawer>
      <ConfirmDialog
        open={rejecting !== null}
        title={`拒绝候选「${rejecting?.title ?? ""}」？`}
        description="候选会标记为已拒绝并保留，不会生成知识项。"
        confirmLabel="拒绝"
        danger
        busy={reject.isPending}
        onConfirm={() => void confirmReject()}
        onCancel={() => setRejecting(null)}
      />
    </section>
  );
}

type AcceptPayload = { title: string; statement: string; item_type: string; source_note: string; evidence_unit_ids: number[] };

function AcceptForm({ candidate, busy, onSubmit, onCancel }: { candidate: Candidate; busy: boolean; onSubmit: (payload: AcceptPayload) => Promise<void>; onCancel: () => void }) {
  const [title, setTitle] = useState(candidate.title);
  const [statement, setStatement] = useState(candidate.statement);
  const [itemType, setItemType] = useState(candidate.item_type);
  const [note, setNote] = useState("");
  const evidenceIds = evidenceIdsFrom(candidate);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim() || !statement.trim() || busy) return;
    void onSubmit({ title: title.trim(), statement: statement.trim(), item_type: itemType, source_note: note.trim(), evidence_unit_ids: evidenceIds });
  }

  return (
    <form className="form-grid" onSubmit={submit} aria-label="接受候选">
      <label className="field">
        <span>标题</span>
        <input value={title} onChange={(event) => setTitle(event.target.value)} required />
      </label>
      <label className="field">
        <span>陈述</span>
        <textarea value={statement} onChange={(event) => setStatement(event.target.value)} rows={5} required />
      </label>
      <label className="field">
        <span>类型</span>
        <select value={itemType} onChange={(event) => setItemType(event.target.value)}>
          {ITEM_TYPES.map((value) => (
            <option key={value} value={value}>
              {ITEM_TYPE_LABELS[value]} ({value})
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>审核备注</span>
        <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="可选" />
      </label>
      <p className="muted">
        关联 Evidence：{evidenceIds.length ? evidenceIds.map((id) => `#${id}`).join(", ") : "来自候选 provenance，接受后可在知识项中调整"} · 置信度 {candidate.origin_confidence ?? "—"}
      </p>
      <div className="modal-actions">
        <button type="button" className="outline-button" onClick={onCancel} disabled={busy}>
          取消
        </button>
        <button type="submit" className="primary-button" disabled={busy || !title.trim() || !statement.trim()}>
          {busy ? "提交中…" : "接受为知识项"}
        </button>
      </div>
    </form>
  );
}
