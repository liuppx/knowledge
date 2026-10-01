import { AnalysisRunsPanel } from "./runs/AnalysisRunsPanel";

export function RunsPage() {
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Analysis runs</p>
          <h1>分析运行</h1>
        </div>
      </header>
      <AnalysisRunsPanel />
    </>
  );
}
