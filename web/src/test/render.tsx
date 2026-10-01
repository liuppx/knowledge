import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { RouterProvider, createMemoryRouter, type RouteObject } from "react-router-dom";

import { createQueryClient } from "../app/queryClient";
import { saveSession } from "../features/auth/session";
import { ToastProvider } from "../ui";

export function loginAs(wallet = "0x1234567890abcdef1234") {
  saveSession({ access_token: "t", refresh_token: "r", wallet_address: wallet });
}

/** Renders `routes` (or a single element) inside the app providers at `path`. */
export function renderRoutes(routes: RouteObject[], path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const client = createQueryClient();
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { router, client };
}

export function renderElement(element: ReactNode, path = "/") {
  return renderRoutes([{ path: "*", element }], path);
}
