import { defineConfig } from 'vite'

export default defineConfig({
    server: {
        proxy: {
            '/auth': 'http://127.0.0.1:8000',
            '/rooms': 'http://127.0.0.1:8000',
            '/ws': {
                target: 'ws://127.0.0.1:8000',
                ws: true
            },
        },
    },
})