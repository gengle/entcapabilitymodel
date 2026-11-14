import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` proxies the API to server.py (start it first: python server.py).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  build: { chunkSizeWarningLimit: 1000 }, // CodeMirror; fine for a local demo
});
