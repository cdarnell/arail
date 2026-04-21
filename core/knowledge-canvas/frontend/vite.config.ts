import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/_integrations/knowledge-canvas/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/knowledge-canvas/api": "http://localhost:8000",
      "/knowledge-canvas/ws":  { target: "ws://localhost:8000", ws: true },
    },
  },
});
