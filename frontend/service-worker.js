// Service Worker de Gocho Barber
// Versión del cache (cambiar cuando actualices archivos importantes)
const CACHE_NAME = 'gocho-barber-v1';

// Archivos que se cachean al instalar (carga rápida offline)
const ARCHIVOS_CACHE = [
    '/',
    '/index.html',
    '/styles.css',
    '/script.js',
    '/manifest.json'
];

// ===== INSTALACIÓN: cachear archivos básicos =====
self.addEventListener('install', (event) => {
    console.log('[Service Worker] Instalando...');
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('[Service Worker] Cacheando archivos');
                return cache.addAll(ARCHIVOS_CACHE);
            })
            .then(() => self.skipWaiting())
    );
});

// ===== ACTIVACIÓN: limpiar caches viejos =====
self.addEventListener('activate', (event) => {
    console.log('[Service Worker] Activando...');
    event.waitUntil(
        caches.keys().then((nombres) => {
            return Promise.all(
                nombres.map((nombre) => {
                    if (nombre !== CACHE_NAME) {
                        console.log('[Service Worker] Borrando cache viejo:', nombre);
                        return caches.delete(nombre);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// ===== FETCH: estrategia =====
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // No cachear llamadas al backend (necesitan datos frescos)
    if (url.origin.includes('gochobarber.onrender.com')) {
        return; // Dejar pasar sin interceptar
    }

    // No cachear peticiones que no son GET
    if (event.request.method !== 'GET') {
        return;
    }

    // Estrategia: cache primero, luego red (para HTML/CSS/JS/imágenes)
    event.respondWith(
        caches.match(event.request)
            .then((response) => {
                if (response) {
                    return response;
                }
                return fetch(event.request)
                    .then((responseFetch) => {
                        // No cachear si la respuesta no es válida
                        if (!responseFetch || responseFetch.status !== 200) {
                            return responseFetch;
                        }
                        // Guardar copia en cache
                        const responseClon = responseFetch.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(event.request, responseClon);
                        });
                        return responseFetch;
                    })
                    .catch(() => {
                        // Si falla la red y no hay cache, mostrar fallback
                        if (event.request.mode === 'navigate') {
                            return caches.match('/index.html');
                        }
                    });
            })
    );
});