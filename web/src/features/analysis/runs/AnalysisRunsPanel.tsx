import { useEffect, useState } from "react";
import { request } from "../../../api/client";

type Run = { id: string; status: string; intent?: string; created_at: string; finished_at: string | null; error_summary: string };

export function AnalysisRunsPanel() {
  const [runs, setRuns] = useState<Run[]>([]); const [error, setError] = useState("");
  useEffect(() => { request<Run[]>("/analysis-runs").then(setRuns).catch((cause) => setError(cause instanceof Error ? cause.message : "加载分析任务失败")); }, []);
  return <section className="panel"><h2>分析任务</h2>{error && <p className="alert">{error}</p>}{runs.length ? runs.map((run) => <article className="evidence" key={run.id}><strong>{run.status} · {run.id}</strong><p>{run.intent || "未填写分析目标"}</p><span className="muted">创建于 {run.created_at}{run.error_summary ? ` · ${run.error_summary}` : ""}</span></article>) : <p className="muted">当前没有可查看的分析任务。分析任务由 Chat 或服务端工作流创建。</p>}</section>;
}
