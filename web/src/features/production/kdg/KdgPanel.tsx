import { useEffect, useState } from "react";

import { messageFor } from "../../../api/client";
import {
  KDG_LAYERS,
  KDG_LAYER_LABELS,
  KDG_RELATION_LABELS,
  KDG_STATUS_LABELS,
  kdgApi,
  type KdgRelationKind,
} from "../../../api/endpoints/kdg";
import type { KnowledgeItem } from "../../../api/endpoints/production";
import { useKdgRefresh, useKdgRelationMutations, useKdgSettingsMutation, useKdgStatusQuery } from "../../../api/queries/kdg";
import { ErrorState, LoadingState, shortenMiddle, useToast } from "../../../ui";
import { requestKdgPubkey, signKdgIntent } from "./walletKdg";

type Props = { kbId: number; itemId: number; items: KnowledgeItem[] };

// 提交后等链上确认:出块很快,但浏览器服务的单元缓存最多几秒才刷新
const POLL_MS = 2000;
const POLL_TIMES = 30;

/**
 * 「上链到知行图」:把当前修订发布为知行图(KnowDoGraph)上的知识单元。
 * 第一次上链创建单元,之后的修订发布为同一单元的新版本。签名在夜莺钱包里完成。
 */
export function KdgPanel({ kbId, itemId, items }: Props) {
  const toast = useToast();
  const status = useKdgStatusQuery(kbId, itemId);
  const settings = useKdgSettingsMutation(kbId, itemId);
  const relations = useKdgRelationMutations(kbId, itemId);
  const refreshStatus = useKdgRefresh(kbId, itemId);
  const [busy, setBusy] = useState<string>("");
  const [domain, setDomain] = useState<string>("");
  const [layer, setLayer] = useState<string>("");
  const [model, setModel] = useState("");
  const [humanEdited, setHumanEdited] = useState(false);
  const [relTarget, setRelTarget] = useState("");
  const [relKind, setRelKind] = useState<KdgRelationKind>("basis");

  const data = status.data;
  useEffect(() => {
    if (!data) return;
    setDomain(data.domain ? String(data.domain) : "");
    setLayer(data.layer ?? "");
  }, [data?.domain, data?.layer]); // eslint-disable-line react-hooks/exhaustive-deps

  if (status.isLoading) return <LoadingState />;
  if (status.isError) return <ErrorState error={status.error} fallback="读取知行图状态失败" />;
  if (!data) return null;
  if (!data.enabled) {
    return <p className="muted">知行图上链未开启（需要管理员配置 KDG_MODE=live 与写入令牌）。</p>;
  }

  const locked = Boolean(data.chain_unit); // 已上链:领域与层级不能再改
  const domains = data.domains ?? [];
  const others = items.filter((it) => it.id !== itemId);
  const itemTitle = (id: number) => others.find((it) => it.id === id)?.title ?? `#${id}`;

  async function saveSettings() {
    try {
      await settings.mutateAsync({
        domain: domain ? Number(domain) : null,
        layer: (layer || null) as never,
        generated_by: { model: model.trim(), human_edited: humanEdited },
      });
      toast.success("已保存上链设置");
    } catch (cause) {
      toast.error(messageFor(cause, "保存失败"));
    }
  }

  async function publish() {
    setBusy("在钱包里确认连接…");
    try {
      const pubkey = await requestKdgPubkey();
      setBusy("准备正文与意图…");
      const prepared = await kdgApi.prepare(kbId, itemId, pubkey);
      setBusy("在钱包里确认签名…");
      const signed = await signKdgIntent(prepared.intent);
      setBusy("提交到知行图…");
      let publication = await kdgApi.submit(kbId, itemId, prepared.publication.id, signed.signed, signed.address);
      for (let i = 0; i < POLL_TIMES && publication.status === "submitted"; i++) {
        setBusy("等待链上确认…");
        await new Promise((ok) => setTimeout(ok, POLL_MS));
        publication = await kdgApi.refresh(kbId, itemId, publication.id);
      }
      if (publication.status === "confirmed") {
        toast.success(`已上链：知行图单元 #${publication.chain_unit} v${publication.chain_version}`);
      } else {
        toast.success("已提交，等待链上确认（稍后刷新查看）");
      }
    } catch (cause) {
      toast.error(messageFor(cause, "上链失败"));
    } finally {
      setBusy("");
      refreshStatus();
    }
  }

  async function checkPending() {
    if (!data?.pending) return;
    try {
      const p = await kdgApi.refresh(kbId, itemId, data.pending.id);
      toast.success(p.status === "confirmed" ? `已上链：知行图单元 #${p.chain_unit} v${p.chain_version}` : `当前状态：${KDG_STATUS_LABELS[p.status] ?? p.status}`);
    } catch (cause) {
      toast.error(messageFor(cause, "刷新失败"));
    } finally {
      refreshStatus();
    }
  }

  return (
    <section aria-label="知行图">
      <h3 style={{ margin: "18px 0 8px" }}>知行图</h3>
      <p className="muted">
        把这条知识发布到公开的知行图（{data.network}）。第一次上链创建单元，之后的修订发布为同一单元的新版本；
        签名在夜莺钱包里完成，Knowledge 不接触你的私钥。链上的核验由其他成员完成。
      </p>
      {data.chain_unit ? (
        <p>
          已上链：
          {data.unit_url ? (
            <a className="text-link" href={data.unit_url} target="_blank" rel="noreferrer">
              知行图单元 #{data.chain_unit} v{data.chain_version}
            </a>
          ) : (
            <span>知行图单元 #{data.chain_unit} v{data.chain_version}</span>
          )}
          {data.current_revision_published ? <span className="muted">（当前修订已上链）</span> : <span className="muted">（当前修订尚未上链）</span>}
        </p>
      ) : null}

      <div className="detail-grid">
        <label className="field">
          <span>领域</span>
          {domains.length ? (
            <select value={domain} onChange={(e) => setDomain(e.target.value)} disabled={locked} aria-label="知行图领域">
              <option value="">请选择</option>
              {domains.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name_zh || d.name_en}（{d.id}）
                </option>
              ))}
            </select>
          ) : (
            <input value={domain} onChange={(e) => setDomain(e.target.value)} disabled={locked} placeholder="领域编号" aria-label="知行图领域" />
          )}
        </label>
        <label className="field">
          <span>层级</span>
          <select value={layer} onChange={(e) => setLayer(e.target.value)} disabled={locked} aria-label="知行图层级">
            <option value="">请选择</option>
            {KDG_LAYERS.map((l) => (
              <option key={l} value={l}>
                {KDG_LAYER_LABELS[l]}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>模型来源（人工撰写留空）</span>
          <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="例如 claude-opus-5-5" aria-label="生成模型" />
        </label>
        <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <input type="checkbox" checked={humanEdited} onChange={(e) => setHumanEdited(e.target.checked)} disabled={!model.trim()} />
          <span>模型生成后经人工修改核对</span>
        </label>
      </div>
      <div className="actions" style={{ marginTop: 8 }}>
        <button type="button" className="outline-button" onClick={saveSettings} disabled={settings.isPending || Boolean(busy)}>
          保存上链设置
        </button>
      </div>

      <h4 style={{ margin: "14px 0 6px" }}>引用（{data.relations.length}）</h4>
      {data.relations.length ? (
        <ul className="link-list">
          {data.relations.map((r) => (
            <li key={r.id}>
              <span>
                {KDG_RELATION_LABELS[r.kind as KdgRelationKind] ?? r.kind} · {itemTitle(r.to_item_id)}
              </span>
              <span className="muted">{r.to_chain_unit ? ` · 知行图 #${r.to_chain_unit}` : " · 尚未上链"}</span>
              <button type="button" className="text-link" onClick={() => relations.remove.mutate(r.id)} aria-label={`删除引用 ${r.id}`}>
                删除
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">没有引用。被「依据」的条目要先上链。</p>
      )}
      <div className="actions" style={{ gap: 8 }}>
        <select value={relKind} onChange={(e) => setRelKind(e.target.value as KdgRelationKind)} aria-label="引用类型">
          {(Object.keys(KDG_RELATION_LABELS) as KdgRelationKind[]).map((k) => (
            <option key={k} value={k}>
              {KDG_RELATION_LABELS[k]}
            </option>
          ))}
        </select>
        <select value={relTarget} onChange={(e) => setRelTarget(e.target.value)} aria-label="被引用的条目">
          <option value="">选择条目</option>
          {others.map((it) => (
            <option key={it.id} value={it.id}>
              #{it.id} {it.title}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="outline-button"
          disabled={!relTarget || relations.add.isPending}
          onClick={async () => {
            try {
              await relations.add.mutateAsync({ toItemId: Number(relTarget), kind: relKind });
              setRelTarget("");
            } catch (cause) {
              toast.error(messageFor(cause, "添加引用失败"));
            }
          }}
        >
          添加引用
        </button>
      </div>

      <div className="actions" style={{ marginTop: 14 }}>
        <button
          type="button"
          className="primary-button"
          onClick={publish}
          disabled={Boolean(busy) || data.current_revision_published || !data.domain || !data.layer}
          title={!data.domain || !data.layer ? "先选领域与层级并保存" : data.current_revision_published ? "当前修订已上链" : ""}
        >
          上链到知行图
        </button>
        {busy ? <span className="muted">{busy}</span> : null}
        {data.pending && data.pending.status === "submitted" ? (
          <button type="button" className="outline-button" onClick={checkPending}>
            刷新上链状态
          </button>
        ) : null}
      </div>

      {data.publications.length ? (
        <ul className="link-list" style={{ marginTop: 10 }} aria-label="上链记录">
          {[...data.publications].reverse().slice(0, 5).map((p) => (
            <li key={p.id}>
              <span>
                {p.op_type === "create" ? "创建单元" : "发布新版本"} · {KDG_STATUS_LABELS[p.status] ?? p.status}
                {p.chain_unit ? ` · #${p.chain_unit} v${p.chain_version}` : ""}
              </span>
              <span className="muted mono">{p.body_sha256 ? ` · 正文 ${shortenMiddle(p.body_sha256, 8)}` : ""}</span>
              {p.error ? <span className="muted"> · {p.error}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
