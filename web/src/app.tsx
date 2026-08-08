import { useEffect, useState } from "react";
import { api } from "./api";

type View = "overview" | "assets" | "items" | "search";

const views: { id: View; label: string; hint: string }[] = [
  { id: "overview", label: "工作区", hint: "运行状态与知识库概览" },
  { id: "assets", label: "资产", hint: "来源文件与同步任务" },
  { id: "items", label: "知识项", hint: "证据、版本与发布" },
  { id: "search", label: "检索验证", hint: "验证已发布知识" },
];

export function App() {
  const [view, setView] = useState<View>("overview");
  const [health, setHealth] = useState("checking");
  const [error, setError] = useState("");

  useEffect(() => {
    api.health().then((result) => setHealth(result.status)).catch(() => setHealth("offline"));
  }, []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-mark">K</div>
        <div className="brand-copy"><strong>Knowledge</strong><span>知识运营控制面</span></div>
        <nav aria-label="主导航">
          {views.map((item) => (
            <button className={view === item.id ? "nav-item active" : "nav-item"} key={item.id} onClick={() => setView(item.id)}>
              <span className="nav-dot" />{item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer"><span className={`status-dot ${health === "ok" ? "online" : ""}`} /> API {health === "ok" ? "已连接" : health}</div>
      </aside>
      <main className="content">
        <header className="topbar"><div><span className="eyebrow">Knowledge / Workspace</span><h1>{views.find((item) => item.id === view)?.label}</h1></div><button className="outline-button" onClick={() => api.health().then(() => setError("")).catch(() => setError("API 暂不可用"))}>刷新状态</button></header>
        {error && <div className="alert">{error}</div>}
        <section className="hero-row"><div><p className="section-kicker">当前工作区</p><h2>知识生产与发布</h2><p className="muted">从 Warehouse 来源到可追溯的正式知识，所有变更都保留证据和版本。</p></div><div className="release-badge"><span className="status-dot online" /> 本地开发环境</div></section>
        <section className="metric-grid"><Metric value="--" label="知识库" /><Metric value="--" label="待处理任务" /><Metric value="--" label="已发布版本" /><Metric value="--" label="近期开销" /></section>
        <section className="panel"><div className="panel-heading"><div><p className="section-kicker">{views.find((item) => item.id === view)?.hint}</p><h3>{view === "overview" ? "工作区准备就绪" : `${views.find((item) => item.id === view)?.label}模块`}</h3></div><span className="panel-code">API-FIRST</span></div><div className="empty-state"><div className="empty-icon">+</div><p>此模块正在从 FastAPI 控制台迁移到 web 工程。</p><span className="muted">领域 API 已保持独立，后续接入真实数据与交互。</span></div></section>
      </main>
    </div>
  );
}

function Metric({ value, label }: { value: string; label: string }) { return <div className="metric"><strong>{value}</strong><span>{label}</span></div>; }
