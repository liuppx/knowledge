import { FormEvent, useState } from "react";

import { ITEM_TYPES, ITEM_TYPE_LABELS } from "../../api/endpoints/production";

export type ItemFormValues = { title: string; statement: string; item_type: string; evidence_unit_ids: number[]; source_note: string };

type Props = { initial?: Partial<ItemFormValues>; submitLabel: string; busy: boolean; onSubmit: (values: ItemFormValues) => Promise<void>; onCancel: () => void };

export function parseIdList(raw: string): number[] {
  return raw
    .split(/[,\s，]+/)
    .map((part) => Number(part.replace(/^#/, "")))
    .filter((id) => Number.isInteger(id) && id > 0);
}

/** Manual knowledge item create / edit form. Editing creates a new revision server-side. */
export function ItemForm({ initial, submitLabel, busy, onSubmit, onCancel }: Props) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [statement, setStatement] = useState(initial?.statement ?? "");
  const [itemType, setItemType] = useState(initial?.item_type ?? "fact");
  const [evidenceIds, setEvidenceIds] = useState((initial?.evidence_unit_ids ?? []).join(", "));
  const [note, setNote] = useState(initial?.source_note ?? "");

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim() || !statement.trim() || busy) return;
    void onSubmit({ title: title.trim(), statement: statement.trim(), item_type: itemType, evidence_unit_ids: parseIdList(evidenceIds), source_note: note.trim() });
  }

  return (
    <form className="form-grid" onSubmit={submit} aria-label="知识项表单">
      <label className="field">
        <span>标题</span>
        <input value={title} onChange={(event) => setTitle(event.target.value)} required />
      </label>
      <label className="field">
        <span>陈述</span>
        <textarea value={statement} onChange={(event) => setStatement(event.target.value)} rows={6} required />
      </label>
      <div className="detail-grid">
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
          <span>关联 Evidence ID（逗号分隔）</span>
          <input value={evidenceIds} onChange={(event) => setEvidenceIds(event.target.value)} placeholder="例如 12, 15" className="mono" />
        </label>
      </div>
      <label className="field">
        <span>来源说明</span>
        <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="为什么新增/修改这条知识" />
      </label>
      <div className="modal-actions">
        <button type="button" className="outline-button" onClick={onCancel} disabled={busy}>
          取消
        </button>
        <button type="submit" className="primary-button" disabled={busy || !title.trim() || !statement.trim()}>
          {busy ? "提交中…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
