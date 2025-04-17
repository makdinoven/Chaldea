import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,               // слушать на всех интерфейсах
    watch: {
      usePolling: true,       // если вам нужен polling
    },
    allowedHosts: 'all'
    // или, чтобы разрешить _все_ хосты (менее безопасно):
    // allowedHosts: 'all',
  },
});
