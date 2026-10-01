import { ChangeEvent, FormEvent, useState } from "react";

import { messageFor } from "../../api/client";
import { useUploadMutation, useUploadsQuery } from "../../api/queries/warehouse";
import { Badge, DataTable, EmptyState, ErrorState, LoadingState, formatBytes, formatDateTime, useToast } from "../../ui";

type BatchResult = { uploaded: string[]; failed: { name: string; error: string }[] };

type Props = { defaultTargetDir: string; canUpload: boolean; onUploaded?: (paths: string[], targetDir: string) => void };

export function UploadsPanel({ defaultTargetDir, canUpload, onUploaded }: Props) {
  const toast = useToast();
  const uploads = useUploadsQuery();
  const upload = useUploadMutation();
  const [files, setFiles] = useState<File[]>([]);
  const [targetDir, setTargetDir] = useState(defaultTargetDir);
  const [progress, setProgress] = useState<string>("");
  const [batch, setBatch] = useState<BatchResult | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!files.length || !canUpload || upload.isPending) return;
    const dir = targetDir.trim() || defaultTargetDir;
    const result: BatchResult = { uploaded: [], failed: [] };
    for (const [index, file] of files.entries()) {
      setProgress(`正在上传 ${index + 1} / ${files.length}：${file.name}`);
      try {
        const response = await upload.mutateAsync({ file, targetDir: dir });
        result.uploaded.push(response.warehouse_path);
      } catch (cause) {
        result.failed.push({ name: file.name, error: messageFor(cause, "上传失败") });
      }
    }
    setProgress("");
    setBatch(result);
    setFiles([]);
    if (result.uploaded.length) {
      toast.success(`已上传 ${result.uploaded.length} 个文件${result.failed.length ? `，失败 ${result.failed.length} 个` : ""}`);
      onUploaded?.(result.uploaded, dir);
    } else if (result.failed.length) {
      toast.error(`${result.failed.length} 个文件上传失败`);
    }
  }

  return (
    <section className="panel">
      <h2>上传文件</h2>
      {!canUpload ? <p className="muted">请先配置写凭证，之后即可把文件上传到 Warehouse 的 uploads 目录。</p> : null}
      <form className="warehouse-form warehouse-upload" onSubmit={submit} aria-label="上传文件">
        <input type="file" multiple disabled={!canUpload} onChange={(event: ChangeEvent<HTMLInputElement>) => setFiles(Array.from(event.target.files ?? []))} aria-label="选择文件" />
        <input value={targetDir} onChange={(event) => setTargetDir(event.target.value)} placeholder="目标目录" aria-label="目标目录" disabled={!canUpload} />
        <button type="submit" className="primary-button" disabled={!canUpload || !files.length || upload.isPending}>
          {upload.isPending ? "上传中…" : `上传${files.length ? ` ${files.length} 个文件` : ""}`}
        </button>
      </form>
      {progress ? <p className="muted">{progress}</p> : null}
      {batch ? (
        <div className={batch.failed.length ? "alert" : "notice"} role="status">
          <span>
            已上传 {batch.uploaded.length} 个文件
            {batch.failed.length ? `，失败 ${batch.failed.length} 个：${batch.failed.map((item) => `${item.name}（${item.error}）`).join("；")}` : ""}
          </span>
        </div>
      ) : null}
      <h3 style={{ marginTop: 18 }}>最近上传</h3>
      {uploads.isLoading ? <LoadingState /> : null}
      {uploads.isError ? <ErrorState error={uploads.error} fallback="加载上传记录失败" onRetry={() => void uploads.refetch()} /> : null}
      {uploads.data ? (
        <DataTable
          dense
          rows={uploads.data}
          rowKey={(record) => record.id}
          empty={<EmptyState title="还没有上传记录" description="上传后可直接在「资产与导入」中以该路径创建导入任务或绑定。" />}
          columns={[
            { key: "name", header: "文件", render: (record) => record.file_name },
            { key: "path", header: "Warehouse 路径", render: (record) => <span className="mono ellipsis">{record.warehouse_target_path}</span> },
            { key: "size", header: "大小", render: (record) => formatBytes(record.size), width: "90px", align: "right" },
            { key: "status", header: "状态", render: (record) => <Badge status={record.status} />, width: "100px" },
            { key: "at", header: "时间", render: (record) => formatDateTime(record.created_at), width: "170px" },
          ]}
        />
      ) : null}
    </section>
  );
}
