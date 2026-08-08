import { useEffect, useState } from "react";
import { request } from "../../../api/client";

type Item = { id: number; item_type: string; origin_type: string; lifecycle_status: string; current_revision_id: number | null };
type Detail = { item: Item; current_revision: { title: string; statement: string; revision_no: number; evidence_links: { evidence_unit_id: number; role: string; summary: string }[] } | null };

export function KnowledgeItemsPanel({ kbId }: { kbId: number }) {
  const [items, setItems] = useState<Item[]>([]); const [detail, setDetail] = useState<Detail | null>(null);
  useEffect(() => { request<Item[]>(`/kbs/${kbId}/items`).then(setItems); setDetail(null); }, [kbId]);
  async function open(item: Item) { setDetail(await request<Detail>(`/kbs/${kbId}/items/${item.id}`)); }
  return <section className="panel"><h2>知识项</h2><div className="items-grid"><div>{items.length ? items.map((item) => <button className="item-row" key={item.id} onClick={() => open(item)}><strong>#{item.id} · {item.item_type}</strong><span>{item.origin_type} · {item.lifecycle_status}</span></button>) : <p className="muted">当前知识库还没有正式知识项。</p>}</div><div className="item-detail">{detail?.current_revision ? <><h3>{detail.current_revision.title}</h3><p>{detail.current_revision.statement}</p><strong>Evidence</strong>{detail.current_revision.evidence_links.map((link) => <p className="muted" key={link.evidence_unit_id}>#{link.evidence_unit_id} · {link.role} · {link.summary}</p>)}</> : <p className="muted">选择知识项查看当前修订和 Evidence 关联。</p>}</div></div></section>;
}
