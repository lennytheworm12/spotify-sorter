import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    // Bind all interfaces so Windows `netsh portproxy` forwarding to the WSL
    // private IP can reach the dev server. The browser still opens the app at
    // the 127.0.0.1 loopback URL (e.g. http://127.0.0.1:5173).
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
  },
})
