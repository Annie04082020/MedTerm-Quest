import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir:'./tests',testMatch:'**/*.spec.ts',testIgnore:'**/android/**',fullyParallel:false,workers:1,
  use:{baseURL:'http://127.0.0.1:5173',headless:true,channel:process.env.PLAYWRIGHT_CHANNEL || undefined},
  webServer:[
    {command:'python -m backend.e2e_server',url:'http://127.0.0.1:8001/api/health',reuseExistingServer:false},
    {command:'npm run dev -- --port 5173 --strictPort',url:'http://127.0.0.1:5173',reuseExistingServer:false,env:{VITE_API_TARGET:'http://127.0.0.1:8001'}},
  ],
});
