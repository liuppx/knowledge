import { FormEvent, useState } from "react";

import { messageFor } from "../../api/client";
import { RELEASE_SELECTION_MODES, type ServiceGrant, type ServicePrincipal } from "../../api/endpoints/grants";
import { RESULT_VIEWS } from "../../api/endpoints/search";
import { useCreateGrantMutation, useCreatePrincipalMutation, useGrantsQuery, usePrincipalsQuery, useUpdateGrantMutation, useUpdatePrincipalMutation } from "../../api/queries/grants";
import { useReleasesQuery } from "../../api/queries/releases";
import { Badge, ConfirmDialog, DataTable, Drawer, EmptyState, ErrorState, LoadingState, formatDateTime, formatRelative, useToast } from "../../ui";

export function GrantsPanel({ kbId }: { kbId: number }) {
  return (
    <>
      <PrincipalsSection />
      <GrantsSection kbId={kbId} />
    </>
  );
}

function PrincipalsSection() {
  const toast = useToast();
  const principals = usePrincipalsQuery();
  const create = useCreatePrincipalMutation();
  const update = useUpdatePrincipalMutation();
  const [serviceId, setServiceId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [apiKey, setApiKey] = useState<{ principal: ServicePrincipal; key: string } | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!serviceId.trim() || !displayName.trim() || create.isPending) return;
    try {
      const result = await create.mutateAsync({ service_id: serviceId.trim(), display_name: displayName.trim(), identity_type: "api_key" });
      setApiKey({ principal: result.principal, key: result.api_key });
      setServiceId("");
      setDisplayName("");
    } catch (cause) {
      toast.error(messageFor(cause, "创建服务主体失败"));
    }
  }

  async function setStatus(principal: ServicePrincipal, status: string) {
    try {
      await update.mutateAsync({ principalId: principal.id, payload: { principal_status: status } });
      toast.success(`${principal.display_name} 已${status === "active" ? "启用" : status === "disabled" ? "停用" : "吊销"}`);
    } catch (cause) {
      toast.error(messageFor(cause, "更新失败"));
    }
  }

  return (
    <section className="panel">
      <h2>服务主体（Service Principal）</h2>
      <p className="muted">消费方应用（Chat / Agent / Project）的身份。API Key 只在创建时显示一次，请立即交付给对应应用。</p>
      <form className="form-row" onSubmit={submit} aria-label="新建服务主体">
        <input value={serviceId} onChange={(event) => setServiceId(event.target.value)} placeholder="service_id，例如 chat.yeying.pub" aria-label="service_id" className="mono" />
        <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="显示名称" aria-label="显示名称" />
        <button type="submit" className="primary-button" disabled={!serviceId.trim() || !displayName.trim() || create.isPending}>
          创建并签发 Key
        </button>
      </form>
      {apiKey ? (
        <div className="reveal-box" role="status">
          <strong>{apiKey.principal.display_name} 的 API Key（仅显示一次）</strong>
          <code className="mono">{apiKey.key}</code>
          <button type="button" className="outline-button" onClick={() => void navigator.clipboard?.writeText(apiKey.key)}>
            复制
          </button>
          <button type="button" className="outline-button" onClick={() => setApiKey(null)}>
            我已保存
          </button>
        </div>
      ) : null}
      {principals.isLoading ? <LoadingState /> : null}
      {principals.isError ? <ErrorState error={principals.error} fallback="加载服务主体失败" onRetry={() => void principals.refetch()} /> : null}
      {principals.data ? (
        <DataTable
          dense
          rows={principals.data}
          rowKey={(principal) => principal.id}
          empty={<EmptyState title="还没有服务主体" description="为每个消费方应用创建一个主体，再按知识库授权。" />}
          columns={[
            { key: "name", header: "名称", render: (principal) => <strong>{principal.display_name}</strong> },
            { key: "service", header: "service_id", render: (principal) => <span className="mono">{principal.service_id}</span> },
            { key: "type", header: "类型", width: "90px", render: (principal) => principal.identity_type },
            { key: "fp", header: "指纹", width: "140px", render: (principal) => <span className="mono ellipsis" title={principal.credential_fingerprint}>{principal.credential_fingerprint}</span> },
            { key: "status", header: "状态", width: "90px", render: (principal) => <Badge status={principal.principal_status} /> },
            {
              key: "actions",
              header: "",
              width: "150px",
              align: "right",
              render: (principal) =>
                principal.principal_status === "revoked" ? null : (
                  <div className="actions">
                    <button type="button" className="outline-button" onClick={() => void setStatus(principal, principal.principal_status === "active" ? "disabled" : "active")}>
                      {principal.principal_status === "active" ? "停用" : "启用"}
                    </button>
                    <button type="button" className="outline-button" onClick={() => void setStatus(principal, "revoked")} aria-label={`吊销 ${principal.display_name}`}>
                      吊销
                    </button>
                  </div>
                ),
            },
          ]}
        />
      ) : null}
    </section>
  );
}

function GrantsSection({ kbId }: { kbId: number }) {
  const toast = useToast();
  const grants = useGrantsQuery(kbId);
  const principals = usePrincipalsQuery();
  const releases = useReleasesQuery(kbId);
  const create = useCreateGrantMutation(kbId);
  const update = useUpdateGrantMutation(kbId);
  const [creating, setCreating] = useState(false);
  const [revoking, setRevoking] = useState<ServiceGrant | null>(null);
  const principalName = (id: number) => principals.data?.find((principal) => principal.id === id)?.display_name ?? `主体 #${id}`;
  const releaseVersion = (id: number | null | undefined) => (id ? (releases.data?.find((release) => release.id === id)?.version ?? `#${id}`) : null);

  async function patch(grant: ServiceGrant, payload: Parameters<typeof update.mutateAsync>[0]["payload"], done: string) {
    try {
      await update.mutateAsync({ grantId: grant.id, payload });
      toast.success(done);
    } catch (cause) {
      toast.error(messageFor(cause, "更新授权失败"));
    }
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>本知识库的授权（Service Grant）</h2>
        <button type="button" className="primary-button" onClick={() => setCreating(true)} disabled={!principals.data?.length}>
          新增授权
        </button>
      </div>
      <p className="muted">授权决定某个服务主体能检索这个知识库的哪个发布版本（最新 / 固定）以及默认结果视图；可随时暂停或吊销。</p>
      {grants.isLoading ? <LoadingState /> : null}
      {grants.isError ? <ErrorState error={grants.error} fallback="加载授权失败" onRetry={() => void grants.refetch()} /> : null}
      {grants.data ? (
        <DataTable
          dense
          rows={grants.data}
          rowKey={(grant) => grant.id}
          empty={<EmptyState title="还没有授权" description={principals.data?.length ? "为服务主体新增一条授权后，它才能通过 /service/search 检索本知识库。" : "先在上方创建服务主体。"} />}
          columns={[
            { key: "principal", header: "服务主体", render: (grant) => <strong>{principalName(grant.service_principal_id)}</strong> },
            { key: "status", header: "状态", width: "90px", render: (grant) => <Badge status={grant.grant_status} /> },
            {
              key: "release",
              header: "发布选择",
              width: "200px",
              render: (grant) => (
                <span>
                  <Badge status={grant.release_selection_mode} /> {grant.release_selection_mode === "pinned_release" ? <span className="mono">{releaseVersion(grant.pinned_release_id) ?? "未指定"}</span> : null}
                </span>
              ),
            },
            { key: "view", header: "默认视图", width: "100px", render: (grant) => <span className="mono">{grant.default_result_mode}</span> },
            { key: "expires", header: "到期", width: "150px", render: (grant) => formatDateTime(grant.expires_at) },
            { key: "used", header: "最近使用", width: "110px", render: (grant) => formatRelative(grant.last_used_at) },
            {
              key: "actions",
              header: "",
              width: "190px",
              align: "right",
              render: (grant) =>
                grant.grant_status === "revoked" ? null : (
                  <div className="actions">
                    {grant.grant_status === "suspended" ? (
                      <button type="button" className="outline-button" onClick={() => void patch(grant, { grant_status: "active" }, "授权已恢复")}>
                        恢复
                      </button>
                    ) : (
                      <button type="button" className="outline-button" onClick={() => void patch(grant, { grant_status: "suspended" }, "授权已暂停")}>
                        暂停
                      </button>
                    )}
                    <button type="button" className="outline-button" onClick={() => setRevoking(grant)} aria-label={`吊销授权 ${grant.id}`}>
                      吊销
                    </button>
                  </div>
                ),
            },
          ]}
        />
      ) : null}
      <Drawer open={creating} title="新增授权" onClose={() => setCreating(false)}>
        <GrantForm
          principals={(principals.data ?? []).filter((principal) => principal.principal_status === "active")}
          releases={releases.data ?? []}
          busy={create.isPending}
          onCancel={() => setCreating(false)}
          onSubmit={async (payload) => {
            try {
              await create.mutateAsync(payload);
              toast.success("授权已创建");
              setCreating(false);
            } catch (cause) {
              toast.error(messageFor(cause, "创建授权失败"));
            }
          }}
        />
      </Drawer>
      <ConfirmDialog
        open={revoking !== null}
        title={`吊销对 ${revoking ? principalName(revoking.service_principal_id) : ""} 的授权？`}
        description="吊销后该主体立即无法检索本知识库，且不可恢复；需要时请重新创建授权。"
        confirmLabel="吊销"
        danger
        busy={update.isPending}
        onConfirm={() => {
          if (!revoking) return;
          void patch(revoking, { grant_status: "revoked" }, "授权已吊销").then(() => setRevoking(null));
        }}
        onCancel={() => setRevoking(null)}
      />
    </section>
  );
}

type GrantFormValues = { service_principal_id: number; release_selection_mode: string; pinned_release_id: number | null; default_result_mode: string; expires_at: string | null };

function GrantForm({ principals, releases, busy, onSubmit, onCancel }: { principals: ServicePrincipal[]; releases: { id: number; version: string; status: string }[]; busy: boolean; onSubmit: (values: GrantFormValues) => Promise<void>; onCancel: () => void }) {
  const [principalId, setPrincipalId] = useState<string>(principals[0] ? String(principals[0].id) : "");
  const [mode, setMode] = useState<string>("latest_published");
  const [pinned, setPinned] = useState<string>("");
  const [view, setView] = useState<string>("compact");
  const [expires, setExpires] = useState("");
  const ready = principalId && (mode !== "pinned_release" || pinned);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready || busy) return;
    void onSubmit({
      service_principal_id: Number(principalId),
      release_selection_mode: mode,
      pinned_release_id: mode === "pinned_release" ? Number(pinned) : null,
      default_result_mode: view,
      expires_at: expires ? new Date(expires).toISOString() : null,
    });
  }

  return (
    <form className="form-grid" onSubmit={submit} aria-label="授权表单">
      <label className="field">
        <span>服务主体</span>
        <select value={principalId} onChange={(event) => setPrincipalId(event.target.value)} required>
          {principals.map((principal) => (
            <option key={principal.id} value={principal.id}>
              {principal.display_name} ({principal.service_id})
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>发布选择</span>
        <select value={mode} onChange={(event) => setMode(event.target.value)}>
          {RELEASE_SELECTION_MODES.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label} — {item.description}
            </option>
          ))}
        </select>
      </label>
      {mode === "pinned_release" ? (
        <label className="field">
          <span>固定到版本</span>
          <select value={pinned} onChange={(event) => setPinned(event.target.value)} required aria-label="固定版本">
            <option value="">选择版本…</option>
            {releases.map((release) => (
              <option key={release.id} value={release.id}>
                {release.version} · {release.status}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <label className="field">
        <span>默认结果视图</span>
        <select value={view} onChange={(event) => setView(event.target.value)}>
          {RESULT_VIEWS.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>到期时间（可选）</span>
        <input type="datetime-local" value={expires} onChange={(event) => setExpires(event.target.value)} />
      </label>
      <div className="modal-actions">
        <button type="button" className="outline-button" onClick={onCancel} disabled={busy}>
          取消
        </button>
        <button type="submit" className="primary-button" disabled={!ready || busy}>
          {busy ? "创建中…" : "创建授权"}
        </button>
      </div>
    </form>
  );
}
