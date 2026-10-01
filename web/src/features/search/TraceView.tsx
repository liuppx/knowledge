import { Badge } from "../../ui";

type Signal = { label: string; value: string; detail?: string };

/**
 * Pull the hybrid-retrieval / rerank markers out of a retrieval trace. The trace
 * may be flat (one search) or nested per mode (search-lab compare), so walk it.
 */
export function collectSignals(trace: unknown, prefix = ""): Signal[] {
  if (!trace || typeof trace !== "object") return [];
  const record = trace as Record<string, unknown>;
  const signals: Signal[] = [];
  const label = (name: string) => (prefix ? `${prefix} · ${name}` : name);
  if (typeof record.vector_signal === "string") {
    const widened = typeof record.vector_widened === "number" ? `向量补召 ${record.vector_widened} 条` : undefined;
    signals.push({ label: label("混合检索"), value: record.vector_signal, detail: widened });
  } else if (record.hybrid_enabled === false) {
    signals.push({ label: label("混合检索"), value: "disabled" });
  }
  if (typeof record.rerank_signal === "string") {
    const count = typeof record.rerank_count === "number" ? `重排 ${record.rerank_count} 条` : undefined;
    signals.push({ label: label("Rerank"), value: record.rerank_signal, detail: count });
  }
  for (const [key, value] of Object.entries(record)) {
    if (value && typeof value === "object" && !Array.isArray(value)) signals.push(...collectSignals(value, prefix ? `${prefix}.${key}` : key));
  }
  return signals;
}

export function signalTone(value: string): "success" | "warning" | "danger" | "info" | "neutral" {
  if (value === "active") return "success";
  if (value.startsWith("degraded")) return "danger";
  if (value === "mock_skipped" || value === "active_no_index") return "warning";
  if (value === "disabled") return "info";
  return "neutral";
}

const SIGNAL_LABELS: Record<string, string> = {
  active: "生效",
  disabled: "已关闭",
  mock_skipped: "mock 跳过",
  active_no_index: "未回填索引",
};

export function TraceView({ trace }: { trace: unknown }) {
  const signals = collectSignals(trace);
  return (
    <>
      {signals.length ? (
        <ul className="signal-list">
          {signals.map((signal, index) => (
            <li key={`${signal.label}-${index}`}>
              <span className="muted">{signal.label}</span>
              <Badge tone={signalTone(signal.value)} status={signal.value}>
                {SIGNAL_LABELS[signal.value] ?? (signal.value.startsWith("degraded") ? `降级：${signal.value.slice("degraded:".length)}` : signal.value)}
              </Badge>
              {signal.detail ? <span className="muted">{signal.detail}</span> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">该日志没有混合检索 / rerank 标记（可能来自旧版本）。</p>
      )}
      <pre className="pre-json">{JSON.stringify(trace ?? {}, null, 2)}</pre>
    </>
  );
}
