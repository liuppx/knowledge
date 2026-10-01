import { useKbId } from "../../app/kbRoute";
import { SearchPanel } from "./SearchPanel";

/** P0 placeholder: existing search-lab compare; P4 replaces with the full retrieval workbench. */
export function SearchPage() {
  const kbId = useKbId();
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Search lab</p>
          <h1>检索台</h1>
        </div>
      </header>
      <SearchPanel kbId={kbId} />
    </>
  );
}
