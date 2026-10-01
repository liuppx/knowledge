import { useSearchParams } from "react-router-dom";

import { useWarehouseStatusQuery } from "../../api/queries/warehouse";
import { useKbId } from "../../app/kbRoute";
import { BindingsPanel } from "./BindingsPanel";
import { DocumentsPanel } from "./DocumentsPanel";
import { SourcesPanel } from "./SourcesPanel";
import { TasksPanel } from "./TasksPanel";

const TABS = [
  { key: "bindings", label: "绑定" },
  { key: "sources", label: "来源" },
  { key: "documents", label: "文档" },
  { key: "tasks", label: "任务" },
] as const;
type Tab = (typeof TABS)[number]["key"];

export function AssetsPage() {
  const kbId = useKbId();
  const [params, setParams] = useSearchParams();
  const status = useWarehouseStatusQuery();
  const taskParam = Number(params.get("task"));
  const selectedTaskId = Number.isInteger(taskParam) && taskParam > 0 ? taskParam : null;
  // A task deep link always lands on the tasks tab.
  const tab: Tab = selectedTaskId ? "tasks" : ((TABS.find((item) => item.key === params.get("tab"))?.key ?? "bindings") as Tab);
  const appRoot = status.data?.current_app_root ?? "/apps/knowledge.yeying.pub";

  function setTab(next: Tab) {
    setParams((current) => {
      const draft = new URLSearchParams(current);
      draft.set("tab", next);
      draft.delete("task");
      return draft;
    });
  }

  function selectTask(taskId: number | null) {
    setParams((current) => {
      const draft = new URLSearchParams(current);
      draft.set("tab", "tasks");
      if (taskId) draft.set("task", String(taskId));
      else draft.delete("task");
      return draft;
    });
  }

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Assets &amp; import</p>
          <h1>资产与导入</h1>
          <p className="muted">绑定 Warehouse 目录 → 创建导入任务 → 文档与 chunk 可见；来源与资产供知识生产使用。</p>
        </div>
      </header>
      <nav className="tabs" aria-label="资产与导入">
        {TABS.map((item) => (
          <button key={item.key} type="button" className={`tab${tab === item.key ? " active" : ""}`} onClick={() => setTab(item.key)} aria-current={tab === item.key ? "page" : undefined}>
            {item.label}
          </button>
        ))}
      </nav>
      {tab === "bindings" ? <BindingsPanel kbId={kbId} appRoot={appRoot} onTaskCreated={selectTask} /> : null}
      {tab === "sources" ? <SourcesPanel kbId={kbId} /> : null}
      {tab === "documents" ? <DocumentsPanel kbId={kbId} onGoToTasks={() => setTab("tasks")} /> : null}
      {tab === "tasks" ? <TasksPanel kbId={kbId} selectedTaskId={selectedTaskId} onSelectTask={selectTask} /> : null}
    </>
  );
}
