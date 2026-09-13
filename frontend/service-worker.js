// Service Worker mínimo
const CACHE_NAME = 'gocho-v2';

self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
    // Handler vacío es suficiente para PWA
});