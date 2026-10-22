/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // In dev, /api is proxied to the FastAPI server so the browser sees a single origin
  // (session + CSRF cookies work without CORS). Override with VITE_API_PROXY_TARGET.
  const target = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    server: { port: 5173, proxy: { "/api": { target, changeOrigin: false } } },
    preview: { port: 4173, proxy: { "/api": { target, changeOrigin: false } } },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      css: false,
      restoreMocks: true,
      testTimeout: 20000,
    },
  };
});
