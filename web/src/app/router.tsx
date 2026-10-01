import { Navigate, createBrowserRouter, type RouteObject } from "react-router-dom";

import { LoginPage } from "../features/auth/LoginPage";
import { RunsPage } from "../features/analysis/RunsPage";
import { AssetsPage } from "../features/assets/AssetsPage";
import { KbIndexPage } from "../features/kbs/KbIndexPage";
import { OverviewPage } from "../features/kbs/OverviewPage";
import { OpsPage } from "../features/ops/OpsPage";
import { ProductionPage } from "../features/production/ProductionPage";
import { ReleasePage } from "../features/release/ReleasePage";
import { SearchPage } from "../features/search/SearchPage";
import { WarehousePage } from "../features/warehouse/WarehousePage";
import { AppShell } from "./AppShell";
import { RequireAuth } from "./RequireAuth";
import { KbLayout, RootRedirect } from "./kbRoute";

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <RootRedirect /> },
          { path: "kbs", element: <KbIndexPage /> },
          {
            path: "kbs/:kbId",
            element: <KbLayout />,
            children: [
              { index: true, element: <Navigate to="overview" replace /> },
              { path: "overview", element: <OverviewPage /> },
              { path: "assets", element: <AssetsPage /> },
              { path: "production", element: <ProductionPage /> },
              { path: "search", element: <SearchPage /> },
              { path: "release", element: <ReleasePage /> },
            ],
          },
          { path: "warehouse", element: <WarehousePage /> },
          { path: "runs", element: <RunsPage /> },
          { path: "ops", element: <OpsPage /> },
          { path: "*", element: <Navigate to="/" replace /> },
        ],
      },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}
