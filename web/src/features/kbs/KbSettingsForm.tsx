import { FormEvent, useState } from "react";

import { messageFor } from "../../api/client";
import type { KnowledgeBase } from "../../api/endpoints/kbs";
import { useUpdateKbMutation } from "../../api/queries/kbs";
import { useToast } from "../../ui";

const CONFIG_DEFAULTS = { chunk_size: 800, chunk_overlap: 120, retrieval_top_k: 6, memory_top_k: 4, embedding_model: "text-embedding-3-small" };
type ConfigKey = keyof typeof CONFIG_DEFAULTS;

function readConfig(kb: KnowledgeBase) {
  const raw = (kb.retrieval_config ?? {}) as Partial<Record<ConfigKey, unknown>>;
  return {
    chunk_size: Number(raw.chunk_size ?? CONFIG_DEFAULTS.chunk_size),
    chunk_overlap: Number(raw.chunk_overlap ?? CONFIG_DEFAULTS.chunk_overlap),
    retrieval_top_k: Number(raw.retrieval_top_k ?? CONFIG_DEFAULTS.retrieval_top_k),
    memory_top_k: Number(raw.memory_top_k ?? CONFIG_DEFAULTS.memory_top_k),
    embedding_model: String(raw.embedding_model ?? CONFIG_DEFAULTS.embedding_model),
  };
}

type Props = { kb: KnowledgeBase; onSaved?: (kb: KnowledgeBase) => void; onCancel?: () => void };

export function KbSettingsForm({ kb, onSaved, onCancel }: Props) {
  const toast = useToast();
  const update = useUpdateKbMutation(kb.id);
  const [name, setName] = useState(kb.name);
  const [description, setDescription] = useState(kb.description ?? "");
  const [config, setConfig] = useState(() => readConfig(kb));

  function setNumber(key: Exclude<ConfigKey, "embedding_model">, value: string) {
    const parsed = Number(value);
    setConfig((current) => ({ ...current, [key]: Number.isFinite(parsed) ? parsed : current[key] }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || update.isPending) return;
    try {
      const saved = await update.mutateAsync({ name: name.trim(), description: description.trim(), retrieval_config: config });
      toast.success("知识库设置已保存");
      onSaved?.(saved);
    } catch (cause) {
      toast.error(messageFor(cause, "保存失败"));
    }
  }

  return (
    <form className="form-grid" onSubmit={submit} aria-label="知识库设置">
      <label className="field">
        <span>名称</span>
        <input value={name} onChange={(event) => setName(event.target.value)} required />
      </label>
      <label className="field">
        <span>描述</span>
        <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} />
      </label>
      <fieldset className="field-group">
        <legend className="eyebrow">检索配置</legend>
        <div className="detail-grid">
          <label className="field">
            <span>chunk_size</span>
            <input type="number" min={100} value={config.chunk_size} onChange={(event) => setNumber("chunk_size", event.target.value)} />
          </label>
          <label className="field">
            <span>chunk_overlap</span>
            <input type="number" min={0} value={config.chunk_overlap} onChange={(event) => setNumber("chunk_overlap", event.target.value)} />
          </label>
          <label className="field">
            <span>retrieval_top_k</span>
            <input type="number" min={1} value={config.retrieval_top_k} onChange={(event) => setNumber("retrieval_top_k", event.target.value)} />
          </label>
          <label className="field">
            <span>memory_top_k</span>
            <input type="number" min={0} value={config.memory_top_k} onChange={(event) => setNumber("memory_top_k", event.target.value)} />
          </label>
          <label className="field">
            <span>embedding_model</span>
            <input value={config.embedding_model} onChange={(event) => setConfig((current) => ({ ...current, embedding_model: event.target.value }))} />
          </label>
        </div>
        <p className="muted">embedding 模型或维度变更后需要全量再索引，见《向量索引运维手册》。</p>
      </fieldset>
      <div className="modal-actions">
        {onCancel ? (
          <button type="button" className="outline-button" onClick={onCancel} disabled={update.isPending}>
            取消
          </button>
        ) : null}
        <button type="submit" className="primary-button" disabled={!name.trim() || update.isPending}>
          {update.isPending ? "保存中…" : "保存"}
        </button>
      </div>
    </form>
  );
}
