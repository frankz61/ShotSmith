import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 前端 25173；/api 与 /files 代理到后端 28000
export default defineConfig({
  plugins: [react()],
  server: {
    port: 25173,
    // 允许通过 ngrok 等隧道访问：前导点 = 该域名及其所有子域（免每次换隧道再改）
    allowedHosts: [".ngrok-free.app", ".ngrok.app", ".ngrok.io"],
    proxy: {
      "/api": "http://localhost:28000",
      "/files": "http://localhost:28000",
    },
  },
});
