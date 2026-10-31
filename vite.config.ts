import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig(({mode})=>({base:mode==='pages'?'/MedTerm-Quest/':'/',build:{target:'es2022'},plugins:[react(),tailwindcss()],server:{watch:{ignored:['**/data/**','**/backend/**','**/test-results/**','**/.pytest_cache/**','**/tests/**']},proxy:{'/api':process.env.VITE_API_TARGET || 'http://127.0.0.1:8000'}}}));
