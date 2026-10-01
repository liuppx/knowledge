import { Activity, Boxes, Database, FlaskConical, Hammer, LayoutDashboard, LogOut, Rocket, Search, Warehouse } from "lucide-react";
import { NavLink, Outlet, matchPath, useLocation, useNavigate } from "react-router-dom";

import { passportApi } from "../features/auth/api";
import { clearSession, readSession } from "../features/auth/session";
import { shortenMiddle } from "../ui";
import { KbSwitcher } from "./KbSwitcher";
import { parseKbId } from "./kbRoute";

export const KB_SECTIONS = [
  { key: "overview", label: "知识库概览", icon: LayoutDashboard },
  { key: "assets", label: "资产与导入", icon: Boxes },
  { key: "production", label: "知识生产", icon: Hammer },
  { key: "search", label: "检索台", icon: Search },
  { key: "release", label: "发布与授权", icon: Rocket },
] as const;

const GLOBAL_SECTIONS = [
  { to: "/warehouse", label: "Warehouse", icon: Warehouse },
  { to: "/runs", label: "分析运行", icon: FlaskConical },
  { to: "/ops", label: "运维", icon: Activity },
] as const;

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const match = matchPath({ path: "/kbs/:kbId/:section/*" }, location.pathname) ?? matchPath({ path: "/kbs/:kbId" }, location.pathname);
  const kbId = parseKbId(match?.params.kbId);
  const section = (match?.params as { section?: string } | undefined)?.section ?? "overview";
  const session = readSession();

  async function logout() {
    await passportApi.logout();
    clearSession();
    navigate("/login", { replace: true });
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-row">
          <div className="brand-mark">K</div>
          <div className="brand-copy">
            <strong>Knowledge</strong>
            <span>知识工作台</span>
          </div>
        </div>
        <nav aria-label="知识库工作台">
          <NavLink to="/kbs" end className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            <Database size={16} /> 知识库
          </NavLink>
          {KB_SECTIONS.map(({ key, label, icon: Icon }) => (
            <NavLink
              key={key}
              to={kbId ? `/kbs/${kbId}/${key}` : "/kbs"}
              className={({ isActive }) => `nav-item${isActive && kbId ? " active" : ""}${kbId ? "" : " disabled"}`}
              aria-disabled={!kbId}
              onClick={(event) => {
                if (!kbId) event.preventDefault();
              }}
            >
              <Icon size={16} /> {label}
            </NavLink>
          ))}
        </nav>
        <nav aria-label="全局" className="nav-secondary">
          {GLOBAL_SECTIONS.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
              <Icon size={16} /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span title={session?.walletAddress}>{session ? shortenMiddle(session.walletAddress) : "未登录"}</span>
          <button type="button" className="icon-button" onClick={() => void logout()} aria-label="退出登录" title="退出登录">
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      <div className="content-column">
        <header className="topbar">
          <KbSwitcher kbId={kbId} section={section} />
          <a className="text-link" href="/docs" target="_blank" rel="noreferrer">
            API 文档
          </a>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
