import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getProvider, loginWithWalletIdentity } from "@yeying-community/web3-bs";

import { messageFor } from "../../api/client";
import { warehouseApi } from "../../api/endpoints/warehouse";
import { readSession } from "../auth/session";
import { Badge, useToast } from "../../ui";

async function warehouseLogin(baseUrl: string, expectedWallet: string): Promise<string> {
  const provider = await getProvider({ preferYeYing: true, timeoutMs: 3000 });
  if (!provider) throw new Error("未检测到可用钱包。");
  const result = await loginWithWalletIdentity({
    baseUrl: `${baseUrl.replace(/\/+$/, "")}/api/v1/public/auth`,
    scopes: ["identity.basic", "identity.wallet", "identity.username", "identity.email"],
    provider,
    credentials: "include",
    storeToken: false,
  });
  const response = result.response as { data?: Record<string, unknown> } | Record<string, unknown>;
  const data = "data" in response && response.data && typeof response.data === "object"
    ? response.data as Record<string, unknown>
    : response as Record<string, unknown>;
  const wallet = String(result.walletAddress || data.walletAddress || data.address || "").toLowerCase();
  if (!wallet || wallet !== expectedWallet.toLowerCase()) {
    throw new Error("Warehouse 登录钱包与当前 Knowledge 钱包不一致，请切换到同一钱包后重试。");
  }
  const token = String(result.token || data.token || "");
  if (!token) throw new Error("Warehouse 登录未返回访问凭证。");
  return token;
}

export function ToolCredentialPanel({ baseUrl }: { baseUrl: string }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const link = useQuery({ queryKey: ["warehouse", "tool-credential"], queryFn: warehouseApi.toolCredential.get });
  const currentWallet = readSession()?.walletAddress ?? "";

  async function connect() {
    setBusy(true);
    try {
      const jwt = await warehouseLogin(baseUrl, currentWallet);
      await warehouseApi.toolCredential.connect(jwt);
      await queryClient.invalidateQueries({ queryKey: ["warehouse", "tool-credential"] });
      toast.success("Warehouse Tool 已连接，凭证有效期为 30 天。");
    } catch (cause) {
      toast.error(messageFor(cause, "连接 Warehouse Tool 失败"));
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    try {
      const jwt = await warehouseLogin(baseUrl, currentWallet);
      await warehouseApi.toolCredential.disconnect(jwt);
      await queryClient.invalidateQueries({ queryKey: ["warehouse", "tool-credential"] });
      toast.success("Warehouse Tool 凭证已撤销。");
    } catch (cause) {
      toast.error(messageFor(cause, "撤销 Warehouse Tool 凭证失败"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Agent Tool 凭证</h2>
        {link.data?.status === "active" ? <Badge status="ok">已连接</Badge> : <Badge status="pending">未连接</Badge>}
      </div>
      <p className="muted">使用当前钱包重新登录 Warehouse，为 Knowledge 创建 30 天有效的受限凭证。权限仅包含资产读写，路径限制在当前 Knowledge 应用目录；凭证密钥由 Knowledge 加密保存，供异步 Run 使用。</p>
      {link.data ? (
        <dl className="detail-grid">
          <div><dt>Credential</dt><dd className="mono">{link.data.credential_id}</dd></div>
          <div><dt>路径范围</dt><dd className="mono">{link.data.path_prefixes.join(", ")}</dd></div>
          <div><dt>到期时间</dt><dd>{new Date(link.data.expires_at).toLocaleString()}</dd></div>
          <div><dt>状态</dt><dd>{link.data.status}</dd></div>
        </dl>
      ) : null}
      {link.isError ? <p role="alert" className="muted">无法读取 Tool 凭证状态：{messageFor(link.error, "请求失败")}</p> : null}
      <div className="actions">
        <button type="button" className="primary-button" disabled={busy || !currentWallet || !baseUrl} onClick={() => void connect()}>
          {busy ? "处理中…" : link.data?.status === "active" ? "续期并轮换" : "连接 Warehouse Tool"}
        </button>
        {link.data?.status === "active" ? <button type="button" className="outline-button" disabled={busy} onClick={() => void disconnect()}>撤销并断开</button> : null}
      </div>
    </section>
  );
}
