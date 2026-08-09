import { useEffect, useState } from "react";
import { SourcesWorkspace } from "../sources/SourcesWorkspace";
import { sourcesApi, type KnowledgeBase } from "../sources/api";
import { SearchPanel } from "../search/SearchPanel";
import { KnowledgeItemsPanel } from "../knowledgeItems/audit/KnowledgeItemsPanel";
import { CandidatesPanel } from "../knowledgeItems/CandidatesPanel";
import { ReleasesPanel } from "../releases/ReleasesPanel";
import { AnalysisRunsPanel } from "../analysis/runs/AnalysisRunsPanel";

export function WorkspaceShell() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]); const [kbId, setKbId] = useState<number>(); const [name, setName] = useState("");
  const refresh = () => sourcesApi.listKnowledgeBases().then((items) => { setKbs(items); setKbId((current) => current ?? items[0]?.id); });
  useEffect(() => { refresh(); }, []);
  async function create() { if (!name.trim()) return; const kb = await sourcesApi.createKnowledgeBase(name.trim()); setName(""); await refresh(); setKbId(kb.id); }
  return <main className="workspace"><header><p className="eyebrow">Knowledge Workspace</p><h1>知识工作台</h1></header><section className="panel"><h2>知识库</h2><div className="form-row"><select value={kbId ?? ""} onChange={(e) => setKbId(Number(e.target.value))}><option value="">选择知识库</option>{kbs.map((kb) => <option key={kb.id} value={kb.id}>{kb.name}</option>)}</select><input value={name} onChange={(e) => setName(e.target.value)} placeholder="新知识库名称"/><button onClick={create}>创建</button></div></section>{kbId ? <><SourcesWorkspace kbId={kbId}/><CandidatesPanel kbId={kbId}/><KnowledgeItemsPanel kbId={kbId}/><ReleasesPanel kbId={kbId}/><SearchPanel kbId={kbId}/><AnalysisRunsPanel /></> : <section className="panel"><p className="muted">创建或选择知识库后开始接入来源。</p></section>}</main>;
}
