import { useEffect, useState } from "react";
import { request } from "../../../api/client";

type Run = { id: string; status: string; intent?: string; created_at: string; finished_at: string | null; error_summary: string };

export function AnalysisRunsPanel() {
  const [runs, setRuns] = useState<Run[]>([]); const [error, setError] = useState(""); const [path, setPath] = useState(""); const [intent, setIntent] = useState("");
  const refresh = () => request<Run[]>("/analysis-runs").then(setRuns).catch((cause) => setError(cause instanceof Error ? cause.message : "加载分析任务失败"));
  useEffect(() => { refresh(); }, []);
  async function create() { if (!path.trim() || !intent.trim()) return; try { setError(""); await request<Run>("/analysis-runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ warehouse_path: path.trim(), intent: intent.trim(), constraints: { allow_sampling: true } }) }); setPath(""); setIntent(""); refresh(); } catch (cause) { setError(cause instanceof Error ? cause.message : "创建分析任务失败"); } }
  return <section className="panel"><h2>分析任务</h2><div className="form-row"><input value={path} onChange={(event) => setPath(event.target.value)} placeholder="Warehouse CSV 或 Excel 路径"/><input value={intent} onChange={(event) => setIntent(event.target.value)} placeholder="分析目标，例如按地区汇总销售额"/><button onClick={create}>创建分析任务</button></div>{error && <p className="alert">{error}</p>}{runs.length ? runs.map((run) => <article className="evidence" key={run.id}><strong>{run.status} · {run.id}</strong><p>{run.intent || "未填写分析目标"}</p><span className="muted">创建于 {run.created_at}{run.error_summary ? ` · ${run.error_summary}` : ""}</span></article>) : <p className="muted">当前没有可查看的分析任务。</p>}</section>;
}
