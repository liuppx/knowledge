import { useState } from "react";
import { PassportLoginPage } from "./features/auth/PassportLoginPage";
import { clearSession, readSession } from "./features/auth/session";

export function App() {
  const [session, setSession] = useState(readSession());
  if (!session) return <PassportLoginPage onAuthenticated={(walletAddress) => setSession({ accessToken: "active", walletAddress })} />;
  return <main className="workspace-placeholder"><div><p className="eyebrow">Knowledge Workspace</p><h1>已通过夜莺通行证登录</h1><p className="muted">来源、Evidence 和知识库工作台会以独立功能模块逐步迁入此 Web 应用。</p><button className="outline-button" onClick={() => { clearSession(); setSession(null); }}>退出登录</button></div></main>;
}
