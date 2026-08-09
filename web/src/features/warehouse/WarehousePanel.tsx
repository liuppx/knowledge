import { ChangeEvent, FormEvent, useEffect, useState } from "react";

import { request } from "../../api/client";

type Credential = {
  id: number;
  key_id: string;
  key_secret_masked: string;
  root_path: string;
  status: string;
};

type WriteCredentialResponse = {
  configured: boolean;
  credential: Credential | null;
};

type UploadResponse = {
  warehouse_path: string;
  file_name: string;
};

function messageFor(cause: unknown, fallback: string) {
  return cause instanceof Error ? cause.message : fallback;
}

export function WarehousePanel() {
  const [credential, setCredential] = useState<Credential | null>(null);
  const [keyId, setKeyId] = useState("");
  const [keySecret, setKeySecret] = useState("");
  const [rootPath, setRootPath] = useState("/apps/knowledge.yeying.pub");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  const loadCredential = async () => {
    try {
      const result = await request<WriteCredentialResponse>("/warehouse/credentials/write");
      setCredential(result.credential);
      if (result.credential) setRootPath(result.credential.root_path);
    } catch (cause) {
      setError(messageFor(cause, "加载 Warehouse 配置失败"));
    }
  };

  useEffect(() => {
    void loadCredential();
  }, []);

  async function saveCredential(event: FormEvent) {
    event.preventDefault();
    if (!keyId.trim() || !keySecret.trim() || !rootPath.trim() || isSaving) return;
    setError("");
    setNotice("");
    setIsSaving(true);
    try {
      const result = await request<Credential>("/warehouse/credentials/write", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key_id: keyId.trim(), key_secret: keySecret.trim(), root_path: rootPath.trim() }),
      });
      setCredential(result);
      setKeySecret("");
      setNotice("Warehouse S3 写凭据已保存。");
    } catch (cause) {
      setError(messageFor(cause, "保存 Warehouse 凭据失败"));
    } finally {
      setIsSaving(false);
    }
  }

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file || !credential || isUploading) return;
    setError("");
    setNotice("");
    setIsUploading(true);
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("target_dir", `${credential.root_path.replace(/\/$/, "")}/uploads`);
      const result = await request<UploadResponse>("/warehouse/upload", { method: "POST", body });
      setFile(null);
      setNotice(`已上传 ${result.file_name}。`);
    } catch (cause) {
      setError(messageFor(cause, "上传文件失败"));
    } finally {
      setIsUploading(false);
    }
  }

  return <section className="panel warehouse-panel">
    <h2>Warehouse</h2>
    {credential ? <p className="muted">已配置 S3 写凭据：{credential.key_id} · {credential.root_path} · {credential.status}</p> : <p className="muted">配置 Warehouse S3 写凭据后即可上传文件。</p>}
    <form className="warehouse-form" onSubmit={saveCredential}>
      <input value={keyId} onChange={(event) => setKeyId(event.target.value)} placeholder="S3 Access Key，例如 AK..." aria-label="S3 Access Key" />
      <input type="password" value={keySecret} onChange={(event) => setKeySecret(event.target.value)} placeholder="S3 Secret" aria-label="S3 Secret" />
      <input value={rootPath} onChange={(event) => setRootPath(event.target.value)} placeholder="S3 root path" aria-label="S3 root path" />
      <button type="submit" disabled={!keyId.trim() || !keySecret.trim() || !rootPath.trim() || isSaving}>{isSaving ? "正在保存" : "保存凭据"}</button>
    </form>
    {credential && <form className="warehouse-form warehouse-upload" onSubmit={upload}>
      <input type="file" onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] ?? null)} aria-label="上传文件" />
      <span className="muted">上传到 {credential.root_path}/uploads</span>
      <button type="submit" disabled={!file || isUploading}>{isUploading ? "正在上传" : "上传文件"}</button>
    </form>}
    {notice && <p className="notice">{notice}</p>}
    {error && <p className="alert" role="alert">{error}</p>}
  </section>;
}
