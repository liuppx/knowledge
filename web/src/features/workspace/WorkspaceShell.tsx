import { FormEvent, useEffect, useState } from "react";

import { AnalysisRunsPanel } from "../analysis/runs/AnalysisRunsPanel";
import { CandidatesPanel } from "../knowledgeItems/CandidatesPanel";
import { KnowledgeItemsPanel } from "../knowledgeItems/audit/KnowledgeItemsPanel";
import { ReleasesPanel } from "../releases/ReleasesPanel";
import { SearchPanel } from "../search/SearchPanel";
import { SourcesWorkspace } from "../sources/SourcesWorkspace";
import { sourcesApi, type KnowledgeBase } from "../sources/api";

function errorMessage(cause: unknown, fallback: string) {
  return cause instanceof Error ? cause.message : fallback;
}

export function WorkspaceShell() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [kbId, setKbId] = useState<number>();
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  const refresh = async () => {
    try {
      const items = await sourcesApi.listKnowledgeBases();
      setKbs(items);
      setKbId((current) => current ?? items[0]?.id);
    } catch (cause) {
      setError(errorMessage(cause, "加载知识库失败"));
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || isCreating) return;
    setError("");
    setIsCreating(true);
    try {
      const kb = await sourcesApi.createKnowledgeBase(name.trim());
      setKbs((current) => [kb, ...current.filter((item) => item.id !== kb.id)]);
      setKbId(kb.id);
      setName("");
    } catch (cause) {
      setError(errorMessage(cause, "创建知识库失败"));
    } finally {
      setIsCreating(false);
    }
  }

  return <main className="workspace">
    <header>
      <p className="eyebrow">Knowledge Workspace</p>
      <h1>知识工作台</h1>
    </header>
    <section className="panel">
      <h2>知识库</h2>
      <form className="form-row" onSubmit={create}>
        <select value={kbId ?? ""} onChange={(event) => setKbId(event.target.value ? Number(event.target.value) : undefined)} aria-label="选择知识库">
          <option value="">选择知识库</option>
          {kbs.map((kb) => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
        </select>
        <input value={name} onChange={(event) => setName(event.target.value)} placeholder="新知识库名称" aria-label="新知识库名称" />
        <button type="submit" disabled={!name.trim() || isCreating}>{isCreating ? "正在创建" : "创建"}</button>
      </form>
      {error && <p className="alert" role="alert">{error}</p>}
    </section>
    {kbId ? <>
      <SourcesWorkspace kbId={kbId} />
      <CandidatesPanel kbId={kbId} />
      <KnowledgeItemsPanel kbId={kbId} />
      <ReleasesPanel kbId={kbId} />
      <SearchPanel kbId={kbId} />
      <AnalysisRunsPanel />
    </> : <section className="panel"><p className="muted">创建或选择知识库后开始接入来源。</p></section>}
  </main>;
}
