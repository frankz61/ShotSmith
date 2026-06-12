import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 前端 25173；/api 与 /files 代理到后端 28000
export default defineConfig({
  plugins: [react()],
  // 依赖预构建固定写明，避免运行中发现新依赖触发整页重载
  optimizeDeps: {
    include: ["react", "react-dom/client", "react/jsx-runtime"],
  },
  server: {
    host: true, // 绑定 0.0.0.0，对局域网/外部设备暴露
    port: 25173,
    // 启动时预转换入口模块链，首次打开页面不再现场编译（冷启动首屏提速）
    warmup: {
      clientFiles: ["./src/main.tsx", "./src/App.tsx", "./src/Login.tsx", "./src/api/client.ts"],
    },
    // 允许通过 ngrok 等隧道访问：前导点 = 该域名及其所有子域（免每次换隧道再改）
    allowedHosts: [".ngrok-free.app", ".ngrok.app", ".ngrok.io", "cloud.frankzhangs.top", "shotsmith.frankz.dpdns.org"],
    proxy: {
      "/api": "http://localhost:28000",
      "/files": "http://localhost:28000",
    },
  },
});
