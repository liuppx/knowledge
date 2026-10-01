import { EmptyState } from "../../ui";

/** P5 fills this with /ops overview, workers, failures and store health. */
export function OpsPage() {
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Operations</p>
          <h1>运维</h1>
        </div>
      </header>
      <section className="panel">
        <EmptyState title="运维视图即将上线" description="队列概览、worker 状态与失败任务将在此展示；当前可使用旧版控制台的运维页。" />
      </section>
    </>
  );
}
