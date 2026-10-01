import { useKbId } from "../../app/kbRoute";
import { SourcesWorkspace } from "../sources/SourcesWorkspace";

/** P0 placeholder: wraps the existing sources panel; P2 replaces it with the full workbench. */
export function AssetsPage() {
  const kbId = useKbId();
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Assets &amp; import</p>
          <h1>资产与导入</h1>
        </div>
      </header>
      <SourcesWorkspace kbId={kbId} />
    </>
  );
}
