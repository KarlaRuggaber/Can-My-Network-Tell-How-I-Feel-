/// <reference types="vitest" />
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The API (FastAPI, port 8600) serves /api; in dev Vite proxies to it.
const api = process.env.CMN_API ?? "http://127.0.0.1:8600";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: { host: "127.0.0.1", port: 5173, proxy: { "/api": api } },
  build: { chunkSizeWarningLimit: 1500 },   // ECharts is one large chunk; fine for a local tool
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test-setup.ts"] },
});
