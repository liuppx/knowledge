import { useKbId } from "../../app/kbRoute";
import { ReleasesPanel } from "../releases/ReleasesPanel";

/** P0 placeholder: existing releases panel; P5 adds hotfix/rollback/diff and grants. */
export function ReleasePage() {
  const kbId = useKbId();
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Release &amp; grants</p>
          <h1>发布与授权</h1>
        </div>
      </header>
      <ReleasesPanel kbId={kbId} />
    </>
  );
}
