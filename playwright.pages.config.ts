import {defineConfig} from '@playwright/test';
export default defineConfig({
 testDir:'./tests/android',testMatch:'**/*.spec.ts',workers:1,timeout:60000,
 use:{baseURL:'http://127.0.0.1:4176/MedTerm-Quest/',headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||undefined,viewport:{width:390,height:844}},
 webServer:{command:'npm run preview:pages -- --port 4176 --strictPort',url:'http://127.0.0.1:4176/MedTerm-Quest/',reuseExistingServer:false},
});
