import { useMemo } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";

import { createQueryClient } from "./app/queryClient";
import { createAppRouter } from "./app/router";
import { ToastProvider } from "./ui";

export function App() {
  const queryClient = useMemo(createQueryClient, []);
  const router = useMemo(createAppRouter, []);
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>
  );
}
