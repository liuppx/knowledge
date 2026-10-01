import { useSearchParams } from "react-router-dom";

import { useKbId } from "../../app/kbRoute";
import { CandidatesPanel } from "./CandidatesPanel";
import { EvidencePanel } from "./EvidencePanel";
import { ItemsPanel } from "./ItemsPanel";

const TABS = [
  { key: "evidence", label: "Evidence" },
  { key: "candidates", label: "候选审核" },
  { key: "items", label: "知识项" },
] as const;
type Tab = (typeof TABS)[number]["key"];

function positiveInt(raw: string | null): number | null {
  const value = Number(raw);
  return Number.isInteger(value) && value > 0 ? value : null;
}

export function ProductionPage() {
  const kbId = useKbId();
  const [params, setParams] = useSearchParams();
  const itemId = positiveInt(params.get("item"));
  const evidenceId = positiveInt(params.get("evidence"));
  // Deep links win over the tab param so a shared URL opens the right drawer.
  const tab: Tab = itemId ? "items" : evidenceId ? "evidence" : ((TABS.find((item) => item.key === params.get("tab"))?.key ?? "evidence") as Tab);

  function update(mutate: (draft: URLSearchParams) => void) {
    setParams((current) => {
      const draft = new URLSearchParams(current);
      mutate(draft);
      return draft;
    });
  }
  const setTab = (next: Tab) =>
    update((draft) => {
      draft.set("tab", next);
      draft.delete("item");
      draft.delete("evidence");
    });
  const selectItem = (id: number | null) =>
    update((draft) => {
      draft.set("tab", "items");
      draft.delete("evidence");
      if (id) draft.set("item", String(id));
      else draft.delete("item");
    });
  const selectEvidence = (id: number | null) =>
    update((draft) => {
      draft.set("tab", "evidence");
      draft.delete("item");
      if (id) draft.set("evidence", String(id));
      else draft.delete("evidence");
    });

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Production</p>
          <h1>知识生产</h1>
          <p className="muted">资产 → Evidence → 候选 → 正式知识项（带修订与证据链）。</p>
        </div>
      </header>
      <nav className="tabs" aria-label="知识生产">
        {TABS.map((item) => (
          <button key={item.key} type="button" className={`tab${tab === item.key ? " active" : ""}`} onClick={() => setTab(item.key)} aria-current={tab === item.key ? "page" : undefined}>
            {item.label}
          </button>
        ))}
      </nav>
      {tab === "evidence" ? <EvidencePanel kbId={kbId} selectedEvidenceId={evidenceId} onSelectEvidence={selectEvidence} onCandidatesGenerated={() => setTab("candidates")} /> : null}
      {tab === "candidates" ? <CandidatesPanel kbId={kbId} onAccepted={selectItem} /> : null}
      {tab === "items" ? <ItemsPanel kbId={kbId} selectedItemId={itemId} onSelectItem={selectItem} onOpenEvidence={selectEvidence} /> : null}
    </>
  );
}
