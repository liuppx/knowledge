import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    allowedHosts: ["knowledge.tidukongjian.com", "test-knowledge.tidukongjian.com"],
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
      "/kbs": "http://127.0.0.1:8000",
      "/service": "http://127.0.0.1:8000",
    },
  },
});
