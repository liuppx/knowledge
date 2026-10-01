import { useEffect, useMemo, useState } from "react";
import { File as FileIcon, Folder, FolderUp } from "lucide-react";

import type { BrowseAccess, WarehouseEntry } from "../../api/endpoints/warehouse";
import { useBrowseQuery, usePreviewQuery, useReadCredentialsQuery, useWriteCredentialQuery } from "../../api/queries/warehouse";
import { Drawer, EmptyState, ErrorState, LoadingState, formatBytes, formatDateTime } from "../../ui";

export type PickedPath = { path: string; scope: "file" | "directory"; access: BrowseAccess };

type Props = {
  initialPath: string;
  /** Called when the user confirms a directory or file. Omit for read-only browsing. */
  onPick?: (picked: PickedPath) => void;
  pickLabel?: string;
};

function crumbs(path: string): { label: string; path: string }[] {
  const parts = path.split("/").filter(Boolean);
  return parts.map((part, index) => ({ label: part, path: `/${parts.slice(0, index + 1).join("/")}` }));
}

/** Warehouse directory browser with credential selector, breadcrumbs and file preview. */
export function WarehouseBrowser({ initialPath, onPick, pickLabel = "选择此目录" }: Props) {
  const readCredentials = useReadCredentialsQuery();
  const writeCredential = useWriteCredentialQuery();
  const [accessKey, setAccessKey] = useState<string>("");
  const [path, setPath] = useState(initialPath);
  const [pathInput, setPathInput] = useState(initialPath);
  const [previewPath, setPreviewPath] = useState<string | null>(null);

  // Default to the first read credential, else the write credential.
  useEffect(() => {
    if (accessKey) return;
    const first = readCredentials.data?.[0];
    if (first) setAccessKey(`read:${first.id}`);
    else if (writeCredential.data?.credential) setAccessKey("write");
  }, [accessKey, readCredentials.data, writeCredential.data]);

  const access = useMemo<BrowseAccess>(() => {
    if (accessKey === "write") return { useWriteCredential: true };
    if (accessKey.startsWith("read:")) return { credentialId: Number(accessKey.slice(5)) };
    return {};
  }, [accessKey]);
  const hasAccess = Boolean(access.credentialId) || Boolean(access.useWriteCredential);
  const browse = useBrowseQuery(hasAccess ? path : null, access);
  const preview = usePreviewQuery(previewPath, access);

  function go(next: string) {
    const normalized = next.trim() || "/";
    setPath(normalized);
    setPathInput(normalized);
  }

  const parent = path.split("/").filter(Boolean).slice(0, -1).join("/");
  const entries = browse.data?.entries ?? [];

  return (
    <div className="browser">
      <div className="browser-toolbar">
        <select aria-label="浏览凭证" value={accessKey} onChange={(event) => setAccessKey(event.target.value)}>
          <option value="">选择浏览凭证…</option>
          {(readCredentials.data ?? []).map((credential) => (
            <option key={credential.id} value={`read:${credential.id}`}>
              读凭证 · {credential.key_id} · {credential.root_path}
            </option>
          ))}
          {writeCredential.data?.credential ? <option value="write">写凭证 · {writeCredential.data.credential.key_id}</option> : null}
        </select>
        <form
          className="browser-path"
          onSubmit={(event) => {
            event.preventDefault();
            go(pathInput);
          }}
        >
          <input value={pathInput} onChange={(event) => setPathInput(event.target.value)} aria-label="浏览路径" className="mono" />
          <button type="submit" className="outline-button">
            前往
          </button>
        </form>
      </div>
      <nav className="breadcrumbs" aria-label="路径">
        <button type="button" className="crumb" onClick={() => go("/")}>
          /
        </button>
        {crumbs(path).map((crumb) => (
          <button key={crumb.path} type="button" className="crumb" onClick={() => go(crumb.path)}>
            {crumb.label}
          </button>
        ))}
      </nav>
      {!hasAccess ? <EmptyState title="请先选择浏览凭证" description="没有读凭证时可先在 Warehouse 页「一键初始化」或手工添加。" /> : null}
      {hasAccess && browse.isLoading ? <LoadingState /> : null}
      {hasAccess && browse.isError ? <ErrorState error={browse.error} fallback="浏览失败" onRetry={() => void browse.refetch()} /> : null}
      {hasAccess && browse.data ? (
        <ul className="entry-list">
          {parent || path !== "/" ? (
            <li>
              <button type="button" className="entry" onClick={() => go(`/${parent}`)}>
                <FolderUp size={16} /> <span>..</span>
              </button>
            </li>
          ) : null}
          {entries.map((entry: WarehouseEntry) => (
            <li key={entry.path}>
              <button type="button" className="entry" onClick={() => (entry.entry_type === "directory" ? go(entry.path) : setPreviewPath(entry.path))}>
                {entry.entry_type === "directory" ? <Folder size={16} /> : <FileIcon size={16} />}
                <span className="ellipsis">{entry.name}</span>
                <span className="muted">{entry.entry_type === "file" ? formatBytes(entry.size) : ""}</span>
                <span className="muted">{formatDateTime(entry.modified_at)}</span>
              </button>
              {onPick && entry.entry_type === "file" ? (
                <button type="button" className="outline-button" onClick={() => onPick({ path: entry.path, scope: "file", access })}>
                  选择文件
                </button>
              ) : null}
            </li>
          ))}
          {!entries.length ? <li className="muted state-row">空目录</li> : null}
        </ul>
      ) : null}
      {onPick && hasAccess ? (
        <div className="actions" style={{ marginTop: 12 }}>
          <button type="button" className="primary-button" onClick={() => onPick({ path, scope: "directory", access })} disabled={!browse.data}>
            {pickLabel}
          </button>
          <span className="muted mono">{path}</span>
        </div>
      ) : null}
      <Drawer open={previewPath !== null} title={previewPath ?? ""} onClose={() => setPreviewPath(null)} width={720}>
        {preview.isLoading ? <LoadingState /> : null}
        {preview.isError ? <ErrorState error={preview.error} fallback="预览失败" /> : null}
        {preview.data ? (
          <>
            <p className="muted">
              {preview.data.file_type} · {formatBytes(preview.data.size)} · {formatDateTime(preview.data.modified_at)}
            </p>
            <pre className="preview">{preview.data.preview || "（无可预览文本）"}</pre>
          </>
        ) : null}
      </Drawer>
    </div>
  );
}
