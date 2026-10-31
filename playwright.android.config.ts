import {defineConfig} from '@playwright/test';
export default defineConfig({
 testDir:'./tests/android',testMatch:'**/*.spec.ts',workers:1,timeout:60000,
 use:{baseURL:'http://127.0.0.1:4175',headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||undefined,viewport:{width:390,height:844}},
 webServer:{command:'npm run mobile:preview -- --port 4175 --strictPort',url:'http://127.0.0.1:4175',reuseExistingServer:false},
});
