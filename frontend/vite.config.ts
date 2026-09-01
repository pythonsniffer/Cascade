import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/** In dev, proxy the API and the WebSocket to the backend so the app runs on one
 *  origin — matching how nginx serves it in the Docker deployment. */
const BACKEND = process.env.VITE_BACKEND ?? "http://localhost:8000";
// Only /api and /frames are proxied: the SPA owns /pnl, /history and /config as
// its own routes, so the API is reached through its /api mount instead.
const API_PATHS = ["/api", "/frames"];

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      ...Object.fromEntries(API_PATHS.map(
        p => [p, { target: BACKEND, changeOrigin: true, ws: true }])),
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
