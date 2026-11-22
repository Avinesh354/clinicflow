import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy keeps the browser same-origin with Django, so session + CSRF cookies just work.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../backend/spa", emptyOutDir: true }, // Django serves the build from here
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000", "/admin": "http://127.0.0.1:8000" } },
});
