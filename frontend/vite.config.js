import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy keeps the browser same-origin with Django, so session + CSRF cookies just work.
// `vite build` -> backend/spa (served by Django). `vite build --mode demo` -> dist-demo (static, for Netlify).
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  build: { outDir: mode === "demo" ? "dist-demo" : "../backend/spa", emptyOutDir: true },
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000", "/admin": "http://127.0.0.1:8000" } },
}));
