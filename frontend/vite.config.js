import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { VitePWA } from 'vite-plugin-pwa';
import { resolve } from 'path';
export default defineConfig({
    plugins: [
        vue(),
        VitePWA({
            strategies: 'injectManifest',
            srcDir: 'src',
            filename: 'sw.ts',
            registerType: 'prompt',
            injectRegister: false,
            manifest: {
                name: 'Školní přehled',
                short_name: 'Škola',
                description: 'Přehled školních informací z Bakaláří',
                theme_color: '#4338ca',
                background_color: '#0a0e1a',
                display: 'standalone',
                orientation: 'portrait',
                start_url: '/',
                scope: '/',
                icons: [
                    { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
                    { src: '/icon-384.png', sizes: '384x384', type: 'image/png' },
                    { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
                    { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
                ],
                screenshots: [
                    { src: '/screenshot-desktop.png', sizes: '1280x720', type: 'image/png', form_factor: 'wide', label: 'Školní přehled - desktop' },
                    { src: '/screenshot-mobile.png', sizes: '390x844', type: 'image/png', form_factor: 'narrow', label: 'Školní přehled - mobil' },
                ],
            },
            injectManifest: {
                globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
            },
            devOptions: {
                enabled: false,
            },
        }),
    ],
    resolve: {
        alias: { '@': resolve(__dirname, 'src') }
    },
    server: {
        proxy: {
            '/api': { target: 'http://localhost:8000', changeOrigin: true }
        }
    }
});
