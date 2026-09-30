import { useEffect, useState } from "react";
import { Fingerprint, Wallet } from "lucide-react";
import { getProvider, loginWithWalletIdentity } from "@yeying-community/web3-bs";
import { ApiError } from "../../api/client";
import { passportApi, tokenFromLogin, type PassportSession } from "./api";
import { saveSession } from "./session";

type Props = { onAuthenticated: (walletAddress: string) => void };

export function PassportLoginPage({ onAuthenticated }: Props) {
  const [session, setSession] = useState<PassportSession | null>(null);
  const [status, setStatus] = useState("使用钱包身份授权登录 Knowledge。");
  const [error, setError] = useState("");
  const [isWalletLogin, setIsWalletLogin] = useState(false);
  const [mode, setMode] = useState<"wallet" | "passport">("wallet");

  useEffect(() => {
    if (!session) return;
    const timer = window.setInterval(async () => {
      try {
        const result = await passportApi.getSession(session.session_id);
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
    setError("");
    setStatus("正在创建夜莺通行证登录会话...");
    try {
      const nextSession = await passportApi.createSession();
      setSession(nextSession);
      setStatus("请在夜莺通行证页面确认登录。");
      window.open(nextSession.verify_url, "knowledge-passport-login", "noopener,noreferrer");
    } catch (cause) {
      setError(messageFor(cause));
      setStatus("登录未开始。");
    }
  }

  function switchMode() {
    setError("");
    setSession(null);
    setMode((current) => current === "wallet" ? "passport" : "wallet");
    setStatus(mode === "wallet" ? "使用夜莺通行证登录，支持 Passkey 与已连接的钱包。" : "使用钱包身份授权登录 Knowledge。");
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
      const result = await loginWithWalletIdentity({ baseUrl: "/auth", provider, storeToken: false });
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

  return <main className="auth-page">
    <section className={`auth-panel ${mode === "wallet" ? "wallet-mode" : "passport-mode"}`} aria-labelledby="passport-login-title">
      <button className="auth-mode-corner" type="button" onClick={switchMode} aria-label={mode === "wallet" ? "切换到通行证登录" : "切换到钱包登录"} title={mode === "wallet" ? "切换到通行证登录" : "切换到钱包登录"}>
        {mode === "wallet" ? <Fingerprint size={30} /> : <Wallet size={30} />}
      </button>
      <div className="brand-mark">K</div>
      <p className="eyebrow">Knowledge Workspace</p>
      <h1 id="passport-login-title">登录 Knowledge</h1>
      <p className="muted">使用夜莺通行证或钱包验证身份。</p>
      {mode === "wallet" ? (
        <button className="primary-button" onClick={() => void startWalletLogin()} disabled={isWalletLogin}>{isWalletLogin ? "正在连接钱包" : "使用钱包登录"}</button>
      ) : (
        <>
          <button className="primary-button" onClick={startLogin}>{session ? "重新发起通行证登录" : "使用夜莺通行证登录"}</button>
          {session && <a className="text-link" href={session.verify_url} target="_blank" rel="noreferrer">无法打开验证页？在新窗口打开</a>}
        </>
      )}
      <p className="auth-status">{status}</p>
      {error && <p className="alert" role="alert">{error}</p>}
    </section>
  </main>;
}

function messageFor(cause: unknown) {
  if (cause instanceof ApiError && cause.status === 503) return "夜莺通行证尚未配置，请联系管理员登记应用回调地址。";
  return cause instanceof Error ? cause.message : "登录失败，请稍后重试。";
}
