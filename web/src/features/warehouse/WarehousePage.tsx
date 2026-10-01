import { WarehousePanel } from "./WarehousePanel";

/** P0 placeholder: write-credential + upload form; P2 adds credentials, bootstrap, browse. */
export function WarehousePage() {
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Warehouse</p>
          <h1>Warehouse</h1>
        </div>
      </header>
      <WarehousePanel />
    </>
  );
}
