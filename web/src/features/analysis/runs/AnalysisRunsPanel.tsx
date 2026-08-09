import { useEffect, useState } from "react";

import { request } from "../../../api/client";

type Run = {
  id: string;
  status: string;
  created_at: string;
  finished_at: string | null;
  error_summary: string;
};

type RunEvent = {
  sequence: number;
  event_type: string;
  stage: string;
  progress: number;
  message: string;
};

type Artifact = {
  id: number;
  artifact_key: string;
  file_name: string;
  status: string;
};

async function downloadArtifact(runId: string, artifact: Artifact) {
  const accessToken = localStorage.getItem("knowledge:access-token");
  const response = await fetch(`/analysis-runs/${runId}/artifacts/${artifact.id}/download`, {
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
  });
  if (!response.ok) throw new Error(`下载产物失败: ${response.status} ${response.statusText}`);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = artifact.file_name;
  link.click();
  URL.revokeObjectURL(url);
}

function messageFor(cause: unknown, fallback: string) {
  return cause instanceof Error ? cause.message : fallback;
}

export function AnalysisRunsPanel() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState("");
  const [path, setPath] = useState("");
  const [intent, setIntent] = useState("");
  const [maxRows, setMaxRows] = useState("");
  const [allowSampling, setAllowSampling] = useState(true);
  const [outputFormats, setOutputFormats] = useState<string[]>(["csv", "xlsx"]);
  const [selected, setSelected] = useState<Run | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  const refresh = async () => {
    try {
      const nextRuns = await request<Run[]>("/analysis-runs");
      setRuns(nextRuns);
      setSelected((current) => current ? nextRuns.find((run) => run.id === current.id) ?? null : null);
    } catch (cause) {
      setError(messageFor(cause, "加载分析任务失败"));
    }
  };

  const loadArtifacts = async (runId: string) => {
    const nextArtifacts = await request<Artifact[]>(`/analysis-runs/${runId}/artifacts`);
    setArtifacts(nextArtifacts);
  };

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (!selected) return;

    const controller = new AbortController();
    const token = localStorage.getItem("knowledge:access-token") || "";
    const runId = selected.id;
    setIsLoadingDetail(true);
    setError("");

    const addEvent = (event: RunEvent) => {
      setEvents((current) => current.some((item) => item.sequence === event.sequence) ? current : [...current, event]);
    };

    const stream = async () => {
      try {
        await loadArtifacts(runId);
        const response = await fetch(`/analysis-runs/${runId}/events/stream`, {
          headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`加载任务事件失败: ${response.status} ${response.statusText}`);
        if (!response.body) throw new Error("任务事件流不可用");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const next = await reader.read();
          if (next.done) break;
          buffer += decoder.decode(next.value, { stream: true });
          const blocks = buffer.split("\n\n");
          buffer = blocks.pop() || "";
          for (const block of blocks) {
            const line = block.split("\n").find((value) => value.startsWith("data: "));
            if (!line) continue;
            try {
              addEvent(JSON.parse(line.slice(6)) as RunEvent);
            } catch {
              setError("无法读取任务事件");
            }
          }
        }
        if (!controller.signal.aborted) {
          await Promise.all([loadArtifacts(runId), refresh()]);
        }
      } catch (cause) {
        if (!controller.signal.aborted) setError(messageFor(cause, "加载任务详情失败"));
      } finally {
        if (!controller.signal.aborted) setIsLoadingDetail(false);
      }
    };

    void stream();
    return () => controller.abort();
  }, [selected?.id]);

  async function create() {
    if (!path.trim() || !intent.trim()) return;
    try {
      setError("");
      const normalizedMaxRows = Number(maxRows);
      const run = await request<Run>("/analysis-runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          warehouse_path: path.trim(),
          intent: intent.trim(),
          constraints: {
            allow_sampling: allowSampling,
            output_formats: outputFormats,
            ...(normalizedMaxRows > 0 ? { max_rows: normalizedMaxRows } : {}),
          },
        }),
      });
      setPath("");
      setIntent("");
      await refresh();
      setEvents([]);
      setArtifacts([]);
      setSelected(run);
    } catch (cause) {
      setError(messageFor(cause, "创建分析任务失败"));
    }
  }

  return <section className="panel">
    <h2>分析任务</h2>
    <div className="form-row">
      <input value={path} onChange={(event) => setPath(event.target.value)} placeholder="Warehouse CSV 或 Excel 路径" />
      <input value={intent} onChange={(event) => setIntent(event.target.value)} placeholder="分析目标，例如按地区汇总销售额" />
      <button onClick={create}>创建分析任务</button>
    </div>
    <div className="analysis-options">
      <input type="number" min="1" value={maxRows} onChange={(event) => setMaxRows(event.target.value)} placeholder="最大处理行数（可选）" />
      <label><input type="checkbox" checked={allowSampling} onChange={(event) => setAllowSampling(event.target.checked)} /> 允许抽样</label>
      {[["csv", "CSV"], ["xlsx", "XLSX"], ["png", "PNG 图表"]].map(([format, label]) => <label key={format}>
        <input
          type="checkbox"
          checked={outputFormats.includes(format)}
          onChange={(event) => setOutputFormats((current) => event.target.checked ? [...current, format] : current.filter((item) => item !== format))}
        /> {label}
      </label>)}
    </div>
    {error && <p className="alert">{error}</p>}
    {runs.length ? runs.map((run) => <article className="evidence" key={run.id}>
      <button className="item-row" onClick={() => { setEvents([]); setArtifacts([]); setSelected(run); }}>
        <strong>{run.status} · {run.id}</strong>
        <span>创建于 {run.created_at}{run.error_summary ? ` · ${run.error_summary}` : ""}</span>
      </button>
    </article>) : <p className="muted">当前没有可查看的分析任务。</p>}
    {selected && <div className="item-detail">
      <h3>任务详情</h3>
      <p className="muted">{selected.status}{isLoadingDetail ? " · 正在同步" : ""}</p>
      <h3>任务事件</h3>
      {events.length ? events.map((event) => <p className="muted" key={event.sequence}>#{event.sequence} · {event.stage || event.event_type} · {event.progress}% · {event.message}</p>) : <p className="muted">尚未收到任务事件。</p>}
      <h3>产物</h3>
      {artifacts.length ? artifacts.map((artifact) => <p className="muted" key={artifact.id}>{artifact.artifact_key} · {artifact.file_name} · {artifact.status} <button onClick={() => void downloadArtifact(selected.id, artifact).catch((cause) => setError(messageFor(cause, "下载产物失败")))}>下载</button></p>) : <p className="muted">尚未生成可查看的产物。</p>}
    </div>}
  </section>;
}
