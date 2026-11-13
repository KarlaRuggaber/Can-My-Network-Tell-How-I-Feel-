/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API (FastAPI, port 8600) serves /api; in dev Vite proxies to it.
const api = process.env.CMN_API ?? "http://127.0.0.1:8600";

export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", port: 5173, proxy: { "/api": api } },
  build: { chunkSizeWarningLimit: 1500 },   // ECharts is one large chunk; fine for a local tool
  test: { environment: "jsdom", globals: true },
});
