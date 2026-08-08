import { useEffect, useState } from "react";
import { request } from "../../api/client";

type Candidate = { id: number; title: string; statement: string; item_type: string; review_status: string; origin_confidence: number | null };

export function CandidatesPanel({ kbId }: { kbId: number }) {
  const [items, setItems] = useState<Candidate[]>([]); const [error, setError] = useState("");
  const refresh = () => request<Candidate[]>(`/kbs/${kbId}/candidates`).then(setItems).catch((cause) => setError(cause instanceof Error ? cause.message : "加载候选失败"));
  useEffect(() => { refresh(); }, [kbId]);
  return <section className="panel"><h2>待审核候选知识</h2>{error && <p className="alert">{error}</p>}{items.length ? <div className="candidate-list">{items.map((item) => <article className="evidence" key={item.id}><strong>{item.title}</strong><p>{item.statement}</p><span className="muted">{item.item_type} · {item.review_status} · 置信度 {item.origin_confidence ?? "-"}</span></article>)}</div> : <p className="muted">当前没有待审核候选。先在来源列表中生成候选知识。</p>}</section>;
}
