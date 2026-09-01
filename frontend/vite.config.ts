import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/** In dev, proxy the API and the WebSocket to the backend so the app runs on one
 *  origin — matching how nginx serves it in the Docker deployment. */
const BACKEND = process.env.VITE_BACKEND ?? "http://localhost:8000";
const API_PATHS = [
  "/health", "/config", "/line", "/twin", "/alerts", "/detections",
  "/pnl", "/history", "/control", "/frames",
];

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      ...Object.fromEntries(API_PATHS.map(p => [p, { target: BACKEND, changeOrigin: true }])),
      "/ws": { target: BACKEND, ws: true, changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
