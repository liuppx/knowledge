import { useEffect } from "react";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";

import { SESSION_EXPIRED_EVENT, readSession } from "../features/auth/session";

/** Gate for everything except /login. Also reacts to the client's session-expired signal. */
export function RequireAuth() {
  const location = useLocation();
  const navigate = useNavigate();
  const session = readSession();

  useEffect(() => {
    const onExpired = () => navigate("/login", { replace: true, state: { from: location.pathname } });
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, [navigate, location.pathname]);

  if (!session) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}
