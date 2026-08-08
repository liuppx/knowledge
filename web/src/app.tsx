import { useState } from "react";
import { PassportLoginPage } from "./features/auth/PassportLoginPage";
import { clearSession, readSession } from "./features/auth/session";
import { SourcesWorkspace } from "./features/sources/SourcesWorkspace";

export function App() {
  const [session, setSession] = useState(readSession());
  if (!session) return <PassportLoginPage onAuthenticated={(walletAddress) => setSession({ accessToken: "active", walletAddress })} />;
  return <><SourcesWorkspace /><button className="logout-button" onClick={() => { clearSession(); setSession(null); }}>退出登录</button></>;
}
