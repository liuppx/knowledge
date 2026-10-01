/// <reference types="vitest/config" />
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Every backend prefix the SPA talks to. Keep in sync with knowledge/main.py routers.
const API_PREFIXES = [
  "/api",
  "/auth",
  "/health",
  "/kbs",
  "/service",
  "/service-principals",
  "/tasks",
  "/warehouse",
  "/ops",
  "/memory",
  "/analysis-runs",
  "/docs",
  "/openapi.json",
];
const BACKEND = process.env.KNOWLEDGE_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    allowedHosts: ["knowledge.tidukongjian.com", "test-knowledge.tidukongjian.com"],
    proxy: Object.fromEntries(API_PREFIXES.map((prefix) => [prefix, BACKEND])),
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
    alias: {
      // web3-bs publishes only a `module` entry (no main/exports); Vite's build resolves
      // it but Node-style test resolution does not, so point tests at the ESM bundle.
      "@yeying-community/web3-bs": fileURLToPath(new URL("./node_modules/@yeying-community/web3-bs/dist/web3-bs.esm.js", import.meta.url)),
    },
  },
});
