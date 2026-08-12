import { useEffect, useState } from "react";
import { request } from "../../api/client";

type Release = { id: number; version: string; status: string; release_note: string; published_at: string | null };
type Detail = { release: Release; items: { knowledge_item_id: number; knowledge_item_revision_id: number; content_health_status: string }[] };

export function ReleasesPanel({ kbId }: { kbId: number }) {
  const [releases, setReleases] = useState<Release[]>([]); const [detail, setDetail] = useState<Detail | null>(null); const [version, setVersion] = useState(""); const [note, setNote] = useState(""); const [error, setError] = useState("");
  const refresh = () => request<Release[]>(`/kbs/${kbId}/releases`).then(setReleases).catch((cause) => setError(cause instanceof Error ? cause.message : "加载发布版本失败"));
  useEffect(() => { refresh(); setDetail(null); }, [kbId]);
  async function open(release: Release) { setDetail(await request<Detail>(`/kbs/${kbId}/releases/${release.id}`)); }
  async function publish() { if (!version.trim()) return; try { const created = await request<Detail>(`/kbs/${kbId}/releases`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ version: version.trim(), release_note: note }) }); setVersion(""); setNote(""); setDetail(created); refresh(); } catch (cause) { setError(cause instanceof Error ? cause.message : "发布失败"); } }
  return <section className="panel"><h2>发布版本</h2><div className="form-row"><input value={version} onChange={(event) => setVersion(event.target.value)} placeholder="版本号，例如 2026.08.09"/><input value={note} onChange={(event) => setNote(event.target.value)} placeholder="发布说明"/><button onClick={publish}>发布当前工作区</button></div>{error && <p className="alert">{error}</p>}<div className="items-grid"><div>{releases.map((release) => <button className="item-row" key={release.id} onClick={() => open(release)}><strong>{release.version}</strong><span>{release.status} · {release.published_at ?? "未发布"}</span></button>)}</div><div className="item-detail">{detail ? <><h3>{detail.release.version}</h3><p>{detail.release.release_note || "无发布说明"}</p><strong>已发布知识项</strong>{detail.items.map((item) => <p className="muted" key={item.knowledge_item_id}>Item #{item.knowledge_item_id} · Revision #{item.knowledge_item_revision_id} · {item.content_health_status}</p>)}</> : <p className="muted">选择版本查看已发布知识项。</p>}</div></div></section>;
}
