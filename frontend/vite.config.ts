import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/** In dev, proxy the API and the WebSocket to the backend so the app runs on one
 *  origin — matching how nginx serves it in the Docker deployment. */
const BACKEND = process.env.VITE_BACKEND ?? "http://localhost:8000";
// Only /api and /frames are proxied: the SPA owns /pnl, /history and /config as
// its own routes, so the API is reached through its /api mount instead.
const API_PATHS = ["/api", "/frames"];

const proxy = {
  ...Object.fromEntries(API_PATHS.map(
    p => [p, { target: BACKEND, changeOrigin: true, ws: true }])),
};

export default defineConfig({
  plugins: [react()],
  // `npm run preview` serves the production bundle with the same routing nginx
  // provides in Docker, so the built app can be tested without the images.
  preview: { host: true, port: 4173, proxy },
  server: {
    host: true,
    port: 5173,
    proxy,
  },
  build: { outDir: "dist", sourcemap: false },
});
