import { useState } from "react";
import { request } from "../../api/client";

type Hit = { result_kind?: string; statement?: string; text?: string; score?: number; source_refs?: string[] };
type Compare = { formal_only: { results?: Hit[] }; evidence_only: { results?: Hit[] }; formal_first: { results?: Hit[] } };

export function SearchPanel({ kbId }: { kbId: number }) {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<Compare | null>(null);
  const [error, setError] = useState("");
  async function run() {
    if (!query.trim()) return;
    try {
      setError("");
      setResult(await request<Compare>(`/kbs/${kbId}/search-lab/compare`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: query.trim(), top_k: 5, result_view: "audit", availability_mode: "allow_all" }) }));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "检索失败"); }
  }
  return <section className="panel"><h2>检索验证</h2><div className="form-row"><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入问题，验证正式知识与 Evidence 命中"/><button onClick={run}>运行对比</button></div>{error && <p className="alert">{error}</p>}{result && <div className="search-grid"><Column title="Formal only" hits={result.formal_only.results ?? []}/><Column title="Evidence only" hits={result.evidence_only.results ?? []}/><Column title="Formal first" hits={result.formal_first.results ?? []}/></div>}</section>;
}

function Column({ title, hits }: { title: string; hits: Hit[] }) {
  return <div><h3>{title}</h3>{hits.length ? hits.map((hit, index) => <article className="evidence" key={index}><strong>{hit.result_kind ?? "result"} · {hit.score?.toFixed(3) ?? "-"}</strong><p>{hit.statement ?? hit.text ?? ""}</p>{hit.source_refs?.length ? <span className="muted">{hit.source_refs.join(", ")}</span> : null}</article>) : <p className="muted">无结果</p>}</div>;
}
