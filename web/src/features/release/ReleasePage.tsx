import { useSearchParams } from "react-router-dom";

import { useKbId } from "../../app/kbRoute";
import { GrantsPanel } from "./GrantsPanel";
import { ReleasesPanel } from "./ReleasesPanel";

const TABS = [
  { key: "releases", label: "发布版本" },
  { key: "grants", label: "授权" },
] as const;
type Tab = (typeof TABS)[number]["key"];

export function ReleasePage() {
  const kbId = useKbId();
  const [params, setParams] = useSearchParams();
  const tab: Tab = (TABS.find((item) => item.key === params.get("tab"))?.key ?? "releases") as Tab;

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Release &amp; grants</p>
          <h1>发布与授权</h1>
          <p className="muted">发布版本固化可检索的知识；授权决定哪个消费方以哪个版本检索。</p>
        </div>
      </header>
      <nav className="tabs" aria-label="发布与授权">
        {TABS.map((item) => (
          <button key={item.key} type="button" className={`tab${tab === item.key ? " active" : ""}`} onClick={() => setParams({ tab: item.key })} aria-current={tab === item.key ? "page" : undefined}>
            {item.label}
          </button>
        ))}
      </nav>
      {tab === "releases" ? <ReleasesPanel kbId={kbId} /> : <GrantsPanel kbId={kbId} />}
    </>
  );
}
