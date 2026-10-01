import { useWarehouseStatusQuery, useWriteCredentialQuery } from "../../api/queries/warehouse";
import { Badge, ErrorState, LoadingState } from "../../ui";
import { BootstrapWizard } from "./BootstrapWizard";
import { ReadCredentialsPanel, WriteCredentialPanel } from "./CredentialsPanels";
import { UploadsPanel } from "./UploadsPanel";
import { WarehouseBrowser } from "./WarehouseBrowser";

export function WarehousePage() {
  const status = useWarehouseStatusQuery();
  const write = useWriteCredentialQuery();
  const appRoot = status.data?.current_app_root ?? "/apps/knowledge.yeying.pub";
  const uploadDir = status.data?.current_app_upload_dir ?? `${appRoot}/uploads`;

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Warehouse</p>
          <h1>Warehouse</h1>
          <p className="muted">凭证、上传与目录浏览。浏览/绑定用读凭证，上传用写凭证，两者语义不同，不要混用。</p>
        </div>
        {status.data ? <Badge status={status.data.credentials_ready ? "ok" : "pending"}>{status.data.credentials_ready ? "凭证就绪" : "凭证未就绪"}</Badge> : null}
      </header>

      {status.isLoading ? <LoadingState /> : null}
      {status.isError ? <ErrorState error={status.error} fallback="加载 Warehouse 状态失败" onRetry={() => void status.refetch()} /> : null}
      {status.data ? (
        <div className="metric-grid">
          <div className="metric">
            <strong className="mono small">{status.data.current_app_id ?? "—"}</strong>
            <span>应用</span>
          </div>
          <div className="metric">
            <strong className="mono small">{status.data.current_app_root ?? "—"}</strong>
            <span>应用根目录</span>
          </div>
          <div className="metric">
            <strong>{status.data.read_credentials_count}</strong>
            <span>读凭证</span>
          </div>
          <div className="metric">
            <strong>
              <Badge status={status.data.write_credential_status ?? "missing"} />
            </strong>
            <span>写凭证 · {status.data.write_root_path ?? "未配置"}</span>
          </div>
        </div>
      ) : null}

      <BootstrapWizard hasWriteCredential={Boolean(write.data?.credential)} />
      {/* Keyed on the resolved root so default paths in the forms follow the real app root. */}
      <div className="two-column" key={appRoot}>
        <WriteCredentialPanel defaultRootPath={appRoot} />
        <ReadCredentialsPanel defaultRootPath={appRoot} />
      </div>
      <UploadsPanel key={uploadDir} defaultTargetDir={uploadDir} canUpload={Boolean(write.data?.credential)} />
      <section className="panel">
        <h2>浏览目录</h2>
        <WarehouseBrowser initialPath={appRoot} />
      </section>
    </>
  );
}
