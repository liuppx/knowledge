import { FormEvent, useState } from "react";

import { messageFor } from "../../api/client";
import type { Credential, CredentialReveal } from "../../api/endpoints/warehouse";
import { warehouseApi } from "../../api/endpoints/warehouse";
import {
  useCreateReadCredentialMutation,
  useDeleteReadCredentialMutation,
  useDeleteWriteCredentialMutation,
  useReadCredentialsQuery,
  useSaveWriteCredentialMutation,
  useWriteCredentialQuery,
} from "../../api/queries/warehouse";
import { Badge, ConfirmDialog, DataTable, EmptyState, ErrorState, LoadingState, formatRelative, useToast } from "../../ui";

type CredentialFormProps = { title: string; submitLabel: string; defaultRootPath: string; onSubmit: (payload: { key_id: string; key_secret: string; root_path: string }) => Promise<unknown>; busy: boolean };

function CredentialForm({ title, submitLabel, defaultRootPath, onSubmit, busy }: CredentialFormProps) {
  const [keyId, setKeyId] = useState("");
  const [keySecret, setKeySecret] = useState("");
  const [rootPath, setRootPath] = useState(defaultRootPath);
  const ready = keyId.trim() && keySecret.trim() && rootPath.trim();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready || busy) return;
    await onSubmit({ key_id: keyId.trim(), key_secret: keySecret.trim(), root_path: rootPath.trim() });
    setKeyId("");
    setKeySecret("");
  }

  return (
    <form className="warehouse-form" onSubmit={submit} aria-label={title}>
      <input value={keyId} onChange={(event) => setKeyId(event.target.value)} placeholder="Access Key ID" aria-label={`${title} Access Key ID`} />
      <input type="password" value={keySecret} onChange={(event) => setKeySecret(event.target.value)} placeholder="Secret" aria-label={`${title} Secret`} autoComplete="off" />
      <input value={rootPath} onChange={(event) => setRootPath(event.target.value)} placeholder="根路径，例如 /apps/knowledge.yeying.pub" aria-label={`${title} 根路径`} />
      <button type="submit" className="primary-button" disabled={!ready || busy}>
        {busy ? "保存中…" : submitLabel}
      </button>
    </form>
  );
}

function RevealedSecret({ reveal, onHide }: { reveal: CredentialReveal; onHide: () => void }) {
  return (
    <div className="reveal-box">
      <span className="mono">
        {reveal.key_id} / {reveal.key_secret}
      </span>
      <button type="button" className="outline-button" onClick={() => void navigator.clipboard?.writeText(reveal.key_secret)}>
        复制 Secret
      </button>
      <button type="button" className="outline-button" onClick={onHide}>
        隐藏
      </button>
    </div>
  );
}

export function ReadCredentialsPanel({ defaultRootPath }: { defaultRootPath: string }) {
  const toast = useToast();
  const credentials = useReadCredentialsQuery();
  const create = useCreateReadCredentialMutation();
  const remove = useDeleteReadCredentialMutation();
  const [revealed, setRevealed] = useState<CredentialReveal | null>(null);
  const [deleting, setDeleting] = useState<Credential | null>(null);

  async function reveal(credential: Credential) {
    try {
      setRevealed(await warehouseApi.readCredentials.reveal(credential.id));
    } catch (cause) {
      toast.error(messageFor(cause, "读取凭证失败"));
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    try {
      await remove.mutateAsync(deleting.id);
      toast.success("读凭证已删除");
      setDeleting(null);
    } catch (cause) {
      toast.error(messageFor(cause, "删除失败：仍有绑定在使用该凭证"));
    }
  }

  return (
    <section className="panel">
      <h2>读凭证</h2>
      <p className="muted">读凭证用于浏览 Warehouse 目录和绑定 Source。一把读凭证对应一个绑定源或一类目录，不要把同一把读凭证复用到无关目录。</p>
      <CredentialForm
        title="新增读凭证"
        submitLabel="添加读凭证"
        defaultRootPath={defaultRootPath}
        busy={create.isPending}
        onSubmit={async (payload) => {
          try {
            await create.mutateAsync(payload);
            toast.success("读凭证已添加");
          } catch (cause) {
            toast.error(messageFor(cause, "添加读凭证失败"));
          }
        }}
      />
      {revealed ? <RevealedSecret reveal={revealed} onHide={() => setRevealed(null)} /> : null}
      {credentials.isLoading ? <LoadingState /> : null}
      {credentials.isError ? <ErrorState error={credentials.error} fallback="加载读凭证失败" onRetry={() => void credentials.refetch()} /> : null}
      {credentials.data ? (
        <DataTable
          dense
          rows={credentials.data}
          rowKey={(credential) => credential.id}
          empty={<EmptyState title="还没有读凭证" description="使用上方「一键初始化」或手工添加 Warehouse 读凭证后，才能浏览目录并绑定来源。" />}
          columns={[
            { key: "key", header: "Key ID", render: (credential) => <span className="mono">{credential.key_id}</span> },
            { key: "root", header: "根路径", render: (credential) => <span className="mono ellipsis">{credential.root_path}</span> },
            { key: "status", header: "状态", render: (credential) => <Badge status={credential.status} />, width: "100px" },
            { key: "used", header: "最近使用", render: (credential) => formatRelative(credential.last_used_at), width: "120px" },
            {
              key: "actions",
              header: "",
              width: "150px",
              align: "right",
              render: (credential) => (
                <div className="actions">
                  <button type="button" className="outline-button" onClick={() => void reveal(credential)}>
                    查看
                  </button>
                  <button type="button" className="outline-button" onClick={() => setDeleting(credential)} aria-label={`删除读凭证 ${credential.key_id}`}>
                    删除
                  </button>
                </div>
              ),
            },
          ]}
        />
      ) : null}
      <ConfirmDialog
        open={deleting !== null}
        title={`删除读凭证 ${deleting?.key_id ?? ""}？`}
        description="仍被绑定使用的读凭证无法删除；请先解绑或更换凭证。"
        confirmLabel="删除"
        danger
        busy={remove.isPending}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleting(null)}
      />
    </section>
  );
}

export function WriteCredentialPanel({ defaultRootPath }: { defaultRootPath: string }) {
  const toast = useToast();
  const write = useWriteCredentialQuery();
  const save = useSaveWriteCredentialMutation();
  const remove = useDeleteWriteCredentialMutation();
  const [revealed, setRevealed] = useState<CredentialReveal | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [editing, setEditing] = useState(false);
  const credential = write.data?.credential ?? null;

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>写凭证</h2>
        {credential ? <Badge status={credential.status} /> : <Badge status="missing">未配置</Badge>}
      </div>
      <p className="muted">写凭证只用于上传文件到 Warehouse；单独配置一把 app 级写凭证，不要当作通用读凭证发放。</p>
      {write.isLoading ? <LoadingState /> : null}
      {write.isError ? <ErrorState error={write.error} fallback="加载写凭证失败" onRetry={() => void write.refetch()} /> : null}
      {credential && !editing ? (
        <dl className="detail-grid">
          <div>
            <dt>Key ID</dt>
            <dd className="mono">{credential.key_id}</dd>
          </div>
          <div>
            <dt>根路径</dt>
            <dd className="mono">{credential.root_path}</dd>
          </div>
          <div>
            <dt>最近验证</dt>
            <dd>{formatRelative(credential.last_verified_at)}</dd>
          </div>
          <div>
            <dt>最近使用</dt>
            <dd>{formatRelative(credential.last_used_at)}</dd>
          </div>
        </dl>
      ) : null}
      {credential === null || editing ? (
        <CredentialForm
          title={credential ? "替换写凭证" : "配置写凭证"}
          submitLabel={credential ? "替换" : "保存写凭证"}
          defaultRootPath={credential?.root_path ?? defaultRootPath}
          busy={save.isPending}
          onSubmit={async (payload) => {
            try {
              await save.mutateAsync(payload);
              setEditing(false);
              toast.success("写凭证已保存");
            } catch (cause) {
              toast.error(messageFor(cause, "保存写凭证失败"));
            }
          }}
        />
      ) : null}
      {revealed ? <RevealedSecret reveal={revealed} onHide={() => setRevealed(null)} /> : null}
      {credential ? (
        <div className="actions" style={{ marginTop: 12 }}>
          <button type="button" className="outline-button" onClick={() => void warehouseApi.writeCredential.reveal().then(setRevealed).catch((cause) => toast.error(messageFor(cause, "读取凭证失败")))}>
            查看 Secret
          </button>
          <button type="button" className="outline-button" onClick={() => setEditing((value) => !value)}>
            {editing ? "取消替换" : "替换"}
          </button>
          <button type="button" className="outline-button" onClick={() => setConfirmingDelete(true)}>
            删除
          </button>
        </div>
      ) : null}
      <ConfirmDialog
        open={confirmingDelete}
        title="删除写凭证？"
        description="删除后将无法上传文件，直到重新配置。已上传的文件不受影响。"
        confirmLabel="删除"
        danger
        busy={remove.isPending}
        onConfirm={() =>
          void remove
            .mutateAsync()
            .then(() => {
              setConfirmingDelete(false);
              toast.success("写凭证已删除");
            })
            .catch((cause) => toast.error(messageFor(cause, "删除失败")))
        }
        onCancel={() => setConfirmingDelete(false)}
      />
    </section>
  );
}
