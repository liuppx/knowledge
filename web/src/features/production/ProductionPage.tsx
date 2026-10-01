import { useKbId } from "../../app/kbRoute";
import { CandidatesPanel } from "../knowledgeItems/CandidatesPanel";
import { KnowledgeItemsPanel } from "../knowledgeItems/audit/KnowledgeItemsPanel";

/** P0 placeholder: existing candidate/item panels; P3 replaces with the production workbench. */
export function ProductionPage() {
  const kbId = useKbId();
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Production</p>
          <h1>知识生产</h1>
        </div>
      </header>
      <CandidatesPanel kbId={kbId} />
      <KnowledgeItemsPanel kbId={kbId} />
    </>
  );
}
