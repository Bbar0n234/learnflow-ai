import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  envDir: '../',  // Искать .env файлы в родительской директории
  plugins: [react()],
  server: {
    host: true,  // Слушать на всех интерфейсах (0.0.0.0), позволяет доступ по 127.0.0.1
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
