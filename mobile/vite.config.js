import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'Cath Hemo',
        short_name: 'CathHemo',
        description: 'Cardiac catheterization hemodynamic reporting',
        theme_color: '#8B1A2B',
        background_color: '#F8F6F3',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg}'],
        runtimeCaching: [
          {
            urlPattern: /^.*\/diagrams\/static\/.*/,
            handler: 'CacheFirst',
            options: { cacheName: 'diagram-images', expiration: { maxEntries: 200 } },
          },
        ],
      },
    }),
  ],
  server: {
    host: true,   // exposes Network URL so phone can connect
    proxy: {
      '/api': 'http://localhost:8000',
      '/diagrams': 'http://localhost:8000',
    },
  },
})
