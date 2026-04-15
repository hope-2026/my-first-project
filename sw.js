const CACHE_NAME = 'mm-chat-v1';
const urlsToCache = [
  '/my-first-project/',
  '/my-first-project/index.html',
  '/my-first-project/manifest.json',
  '/my-first-project/icon-192.png',
  '/my-first-project/icon-512.png'
];

// Installation - Cache befüllen
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Cache geöffnet');
        return cache.addAll(urlsToCache);
      })
      .then(() => self.skipWaiting())
  );
});

// Aktivierung - Alte Caches löschen
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            console.log('Alter Cache gelöscht:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch - Cache-First Strategie für App-Dateien, Network-First für API
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  
  // API-Anfragen immer über Netzwerk
  if (url.hostname === 'openrouter.ai' || url.hostname.includes('supabase')) {
    event.respondWith(
      fetch(event.request)
        .catch(() => new Response(JSON.stringify({ error: 'Offline' }), {
          headers: { 'Content-Type': 'application/json' }
        }))
    );
    return;
  }
  
  // App-Dateien: Cache-First
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response;
        }
        return fetch(event.request)
          .then(response => {
            // Nur erfolgreiche Responses cachen
            if (!response || response.status !== 200 || response.type !== 'basic') {
              return response;
            }
            const responseToCache = response.clone();
            caches.open(CACHE_NAME)
              .then(cache => {
                cache.put(event.request, responseToCache);
              });
            return response;
          });
      })
      .catch(() => {
        // Offline-Fallback
        return caches.match('/my-first-project/index.html');
      })
  );
});
