import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 前端 25173；/api 与 /files 代理到后端 28000
export default defineConfig({
  plugins: [react()],
  server: {
    port: 25173,
    proxy: {
      "/api": "http://localhost:28000",
      "/files": "http://localhost:28000",
    },
  },
});
