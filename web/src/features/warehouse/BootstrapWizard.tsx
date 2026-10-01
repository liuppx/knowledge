import { useState } from "react";

import { messageFor } from "../../api/client";
import type { BootstrapInitializeRequest, BootstrapInitializeResponse } from "../../api/endpoints/warehouse";
import { warehouseApi } from "../../api/endpoints/warehouse";
import { useWarehouseStatusQuery, warehouseKeys } from "../../api/queries/warehouse";
import { readSession } from "../auth/session";
import { Badge, ConfirmDialog, useToast } from "../../ui";
import { signChallengeWithWallet } from "./walletSign";
import { useQueryClient } from "@tanstack/react-query";

type Mode = BootstrapInitializeRequest["mode"];
type Stage = "idle" | "requesting_challenge" | "signing_challenge" | "initializing" | "ready" | "failed";

const MODES: { value: Mode; label: string; description: string }[] = [
  { value: "uploads_bundle", label: "uploads 读写凭证（推荐）", description: "为当前应用的 uploads 目录生成一把写凭证和一把读凭证，可直接上传并绑定。" },
  { value: "app_root_write", label: "app 根写凭证", description: "只为应用根目录生成写凭证，适合已有读凭证、需要跨目录写入的场景。" },
];

const STAGE_LABELS: Record<Stage, string> = {
  idle: "",
  requesting_challenge: "正在向 Knowledge 请求 Warehouse challenge…",
  signing_challenge: "请在钱包中签名 Warehouse challenge…",
  initializing: "Knowledge 正在代为完成 Warehouse 初始化…",
  ready: "初始化完成",
  failed: "初始化失败",
};

type Props = { hasWriteCredential: boolean };

/** One-click Warehouse credential bootstrap: challenge → wallet signature → initialize. */
export function BootstrapWizard({ hasWriteCredential }: Props) {
  const toast = useToast();
  const client = useQueryClient();
  const status = useWarehouseStatusQuery();
  const [mode, setMode] = useState<Mode>("uploads_bundle");
  const [stage, setStage] = useState<Stage>("idle");
  const [error, setError] = useState("");
  const [result, setResult] = useState<BootstrapInitializeResponse | null>(null);
  const [confirming, setConfirming] = useState(false);

  const busy = stage === "requesting_challenge" || stage === "signing_challenge" || stage === "initializing";

  async function run() {
    setError("");
    setResult(null);
    try {
      setStage("requesting_challenge");
      const challenge = await warehouseApi.bootstrapChallenge();
      setStage("signing_challenge");
      const expected = readSession()?.walletAddress ?? challenge.wallet_address;
      const { signature } = await signChallengeWithWallet(challenge.challenge, expected);
      setStage("initializing");
      const response = await warehouseApi.bootstrapInitialize({ mode, signature });
      setResult(response);
      setStage("ready");
      await Promise.all([
        client.invalidateQueries({ queryKey: warehouseKeys.status }),
        client.invalidateQueries({ queryKey: warehouseKeys.readCredentials }),
        client.invalidateQueries({ queryKey: warehouseKeys.writeCredential }),
      ]);
      toast.success(`${response.mode_label} 初始化完成`);
    } catch (cause) {
      setStage("failed");
      setError(messageFor(cause, "Warehouse 初始化失败，请稍后重试。"));
    }
  }

  function start() {
    if (hasWriteCredential) setConfirming(true);
    else void run();
  }

  const targetPath = mode === "app_root_write" ? status.data?.current_app_root : status.data?.current_app_upload_dir;

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>一键初始化凭证</h2>
        {stage !== "idle" ? <Badge status={stage === "ready" ? "ok" : stage === "failed" ? "failed" : "running"}>{STAGE_LABELS[stage]}</Badge> : null}
      </div>
      <p className="muted">用登录钱包签名一次 challenge，由 Knowledge 代为在 Warehouse 创建最小权限凭证并保存，无需手工复制 Access Key。</p>
      <div className="mode-grid">
        {MODES.map((item) => (
          <label key={item.value} className={`mode-option${mode === item.value ? " selected" : ""}`}>
            <input type="radio" name="bootstrap-mode" value={item.value} checked={mode === item.value} onChange={() => setMode(item.value)} disabled={busy} />
            <div>
              <strong>{item.label}</strong>
              <p className="muted">{item.description}</p>
            </div>
          </label>
        ))}
      </div>
      <div className="actions">
        <button type="button" className="primary-button" onClick={start} disabled={busy}>
          {busy ? STAGE_LABELS[stage] : "使用钱包签名并初始化"}
        </button>
        <span className="muted mono">目标路径：{targetPath ?? "—"}</span>
      </div>
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}
      {result ? (
        <dl className="detail-grid" style={{ marginTop: 12 }}>
          <div>
            <dt>模式</dt>
            <dd>{result.mode_label}</dd>
          </div>
          <div>
            <dt>目标路径</dt>
            <dd className="mono">{result.target_path}</dd>
          </div>
          <div>
            <dt>写凭证 Key</dt>
            <dd className="mono">{result.write_key_id}</dd>
          </div>
          <div>
            <dt>读凭证 Key</dt>
            <dd className="mono">{result.read_key_id ?? "—"}</dd>
          </div>
        </dl>
      ) : null}
      <ConfirmDialog
        open={confirming}
        title="覆盖当前写凭证？"
        description="该操作会用 Warehouse 临时授权生成的新写凭证覆盖当前写凭证配置。已有读凭证不会被删除。"
        confirmLabel="继续初始化"
        onConfirm={() => {
          setConfirming(false);
          void run();
        }}
        onCancel={() => setConfirming(false)}
      />
    </section>
  );
}
