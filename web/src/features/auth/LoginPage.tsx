import { useLocation, useNavigate } from "react-router-dom";

import { PassportLoginPage } from "./PassportLoginPage";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  return <PassportLoginPage onAuthenticated={() => navigate(from && from !== "/login" ? from : "/", { replace: true })} />;
}
