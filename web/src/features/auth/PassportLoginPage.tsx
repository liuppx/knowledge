import { useEffect, useState } from "react";
import {
  ArrowUpRight,
  CheckCircle2,
  Database,
  FileCheck2,
  Fingerprint,
  LoaderCircle,
  Network,
  ShieldCheck,
  Wallet,
} from "lucide-react";
import { getProvider, loginWithWalletIdentity } from "@yeying-community/web3-bs";
import { ApiError } from "../../api/client";
import { passportApi, tokenFromLogin, type PassportSession } from "./api";
import { saveSession } from "./session";

type Props = { onAuthenticated: (walletAddress: string) => void };
type LoginMode = "wallet" | "passport";

const MODE_STATUS: Record<LoginMode, string> = {
  wallet: "使用钱包签发的身份凭证完成登录。",
  passport: "通过夜莺通行证完成 Passkey 或钱包验证。",
};

const KNOWLEDGE_FLOW = [
  { label: "接入来源", detail: "文档、表格与业务系统", icon: Database },
  { label: "固化证据", detail: "解析、检索与人工复核", icon: FileCheck2 },
  { label: "可信发布", detail: "版本、授权与可追溯引用", icon: Network },
] as const;

export function PassportLoginPage({ onAuthenticated }: Props) {
  const [session, setSession] = useState<PassportSession | null>(null);
  const [status, setStatus] = useState(MODE_STATUS.wallet);
  const [error, setError] = useState("");
  const [isWalletLogin, setIsWalletLogin] = useState(false);
  const [isPassportLogin, setIsPassportLogin] = useState(false);
  const [mode, setMode] = useState<LoginMode>("wallet");

  useEffect(() => {
    if (!session) return;
    const timer = window.setInterval(async () => {
      try {
        const result = await passportApi.getSession(session.session_id);
        if (result.status === "failed" || result.status === "expired") {
          window.clearInterval(timer);
          setSession(null);
          setError(result.status === "expired" ? "通行证登录已过期，请重新发起。" : "夜莺身份验证失败，请重新发起登录。");
          setStatus("登录未完成。");
          return;
        }
        if (result.status !== "completed" || !result.token) return;
        saveSession(result.token);
        onAuthenticated(result.token.wallet_address);
      } catch (cause) {
        setError(messageFor(cause));
        window.clearInterval(timer);
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [session, onAuthenticated]);

  async function startLogin() {
    if (isPassportLogin) return;
    setError("");
    setIsPassportLogin(true);
    setStatus("正在创建夜莺通行证登录会话...");
    const popup = window.open("about:blank", "knowledge-passport-login");
    if (!popup) {
      setError("浏览器阻止了验证窗口，请允许弹出窗口后重试。");
      setStatus("登录未开始。");
      setIsPassportLogin(false);
      return;
    }
    try {
      const nextSession = await passportApi.createSession();
      setSession(nextSession);
      setStatus("请在夜莺通行证页面确认登录。");
      popup.location.assign(nextSession.verify_url);
    } catch (cause) {
      popup.close();
      setError(messageFor(cause));
      setStatus("登录未开始。");
    } finally {
      setIsPassportLogin(false);
    }
  }

  function selectMode(nextMode: LoginMode) {
    if (nextMode === mode) return;
    setError("");
    setSession(null);
    setMode(nextMode);
    setStatus(MODE_STATUS[nextMode]);
  }

  async function startWalletLogin() {
    if (isWalletLogin) return;
    setError("");
    setIsWalletLogin(true);
    setStatus("正在连接钱包...");
    try {
      const provider = await getProvider({ preferYeYing: true, timeoutMs: 3000 });
      if (!provider) throw new Error("未检测到可用钱包，请安装并解锁夜莺钱包或兼容钱包扩展。");
      setStatus("请在钱包中确认钱包身份授权...");
      const result = await loginWithWalletIdentity({
        baseUrl: "/auth",
        scopes: ["identity.basic", "identity.wallet", "identity.username", "identity.email"],
        provider,
        storeToken: false,
      });
      const token = tokenFromLogin(result.response);
      saveSession(token);
      onAuthenticated(token.wallet_address);
    } catch (cause) {
      setError(messageFor(cause));
      setStatus("钱包登录未完成。");
    } finally {
      setIsWalletLogin(false);
    }
  }

  const busy = mode === "wallet" && isWalletLogin;

  return (
    <main className="auth-page">
      <section className="auth-story" aria-labelledby="knowledge-story-title">
        <div className="auth-brand">
          <span className="auth-brand-mark" aria-hidden="true">K</span>
          <span>
            <strong>Knowledge</strong>
            <small>夜莺可信知识工作台</small>
          </span>
        </div>

        <div className="auth-story-copy">
          <p className="auth-kicker">从原始资料到可信知识</p>
          <h1 id="knowledge-story-title">让每条知识，都能回到它的证据。</h1>
          <p>在一个工作台里接入来源、沉淀证据、验证检索效果，并把经过审核的知识安全发布给团队与智能体。</p>
        </div>

        <ol className="knowledge-flow" aria-label="Knowledge 工作流">
          {KNOWLEDGE_FLOW.map(({ label, detail, icon: Icon }, index) => (
            <li key={label}>
              <span className="knowledge-flow-icon"><Icon size={19} aria-hidden="true" /></span>
              <span className="knowledge-flow-copy">
                <strong>{label}</strong>
                <small>{detail}</small>
              </span>
              {index < KNOWLEDGE_FLOW.length - 1 && <span className="knowledge-flow-line" aria-hidden="true" />}
            </li>
          ))}
        </ol>

        <p className="auth-story-footnote"><ShieldCheck size={17} aria-hidden="true" /> 身份、授权与知识版本保持可审计</p>
      </section>

      <section className="auth-access" aria-labelledby="passport-login-title">
        <div className="auth-access-inner">
          <div className="auth-mobile-brand" aria-hidden="true">
            <span className="auth-brand-mark">K</span>
            <strong>Knowledge</strong>
          </div>

          <header className="auth-heading">
            <p>身份验证</p>
            <h2 id="passport-login-title">进入 Knowledge</h2>
            <span>选择一种方式确认你的夜莺身份。</span>
          </header>

          <div className="auth-mode-switch" role="group" aria-label="选择登录方式">
            <button
              type="button"
              className={mode === "wallet" ? "active" : ""}
              aria-pressed={mode === "wallet"}
              disabled={isWalletLogin || isPassportLogin}
              onClick={() => selectMode("wallet")}
            >
              <Wallet size={18} aria-hidden="true" /> 钱包身份
            </button>
            <button
              type="button"
              className={mode === "passport" ? "active" : ""}
              aria-pressed={mode === "passport"}
              disabled={isWalletLogin || isPassportLogin}
              onClick={() => selectMode("passport")}
            >
              <Fingerprint size={18} aria-hidden="true" /> 夜莺通行证
            </button>
          </div>

          <div className="auth-method" key={mode}>
            <div className="auth-method-heading">
              <span className="auth-method-icon" aria-hidden="true">
                {mode === "wallet" ? <Wallet size={22} /> : <Fingerprint size={22} />}
              </span>
              <span>
                <strong>{mode === "wallet" ? "使用钱包身份" : "使用夜莺通行证"}</strong>
                <small>{mode === "wallet" ? "在钱包扩展中查看并确认授权范围" : "支持 Passkey 与已连接的钱包"}</small>
              </span>
            </div>

            {mode === "wallet" ? (
              <button className="primary-button auth-submit" type="button" onClick={() => void startWalletLogin()} disabled={isWalletLogin}>
                {isWalletLogin ? <LoaderCircle className="spin" size={19} aria-hidden="true" /> : <Wallet size={19} aria-hidden="true" />}
                {isWalletLogin ? "正在连接钱包" : "连接钱包并继续"}
              </button>
            ) : (
              <>
                <button className="primary-button auth-submit" type="button" onClick={startLogin} disabled={isPassportLogin}>
                  {isPassportLogin ? <LoaderCircle className="spin" size={19} aria-hidden="true" /> : <Fingerprint size={19} aria-hidden="true" />}
                  {isPassportLogin ? "正在创建登录请求" : session ? "重新发起通行证登录" : "打开夜莺通行证"}
                </button>
                {session && (
                  <a className="auth-external-link" href={session.verify_url} target="_blank" rel="noreferrer">
                    验证页没有打开？在新窗口继续 <ArrowUpRight size={15} aria-hidden="true" />
                  </a>
                )}
              </>
            )}
          </div>

          <div className={`auth-feedback${error ? " has-error" : ""}`} role={error ? "alert" : "status"} aria-live="polite" aria-atomic="true">
            {error ? <span className="auth-feedback-mark">!</span> : busy ? <LoaderCircle className="spin" size={18} aria-hidden="true" /> : <CheckCircle2 size={18} aria-hidden="true" />}
            <span>{error || status}</span>
          </div>

          <ul className="auth-assurances" aria-label="登录安全说明">
            <li>授权内容在钱包中确认</li>
            <li>登录令牌仅保存于当前浏览器</li>
            <li>可随时从工作台退出</li>
          </ul>
        </div>
      </section>
    </main>
  );
}

function messageFor(cause: unknown) {
  if (cause instanceof ApiError && cause.status === 503) return cause.detail && typeof cause.detail === "string" ? cause.detail : "夜莺通行证尚未配置，请联系管理员登记应用回调地址。";
  return cause instanceof Error ? cause.message : "登录失败，请稍后重试。";
}
