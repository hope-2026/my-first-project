const CACHE_NAME = 'mm-chat-v3';
const urlsToCache = [
  '/',
  '/index.html',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => Promise.all(
      cacheNames.map(name => name !== CACHE_NAME ? caches.delete(name) : null)
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  // POST-Anfragen niemals cachen (Browser-Einschränkung — sonst Fehler bei Netlify Functions)
  if (event.request.method === 'POST') {
    return;
  }

  const url = new URL(event.request.url);

  // Netlify Functions und externe APIs immer direkt übers Netzwerk
  if (url.pathname.startsWith('/.netlify/') ||
      url.hostname === 'openrouter.ai' ||
      url.hostname.includes('openai.com')) {
    event.respondWith(
      fetch(event.request).catch(() =>
        new Response(JSON.stringify({ error: 'Offline' }), {
          headers: { 'Content-Type': 'application/json' }
        })
      )
    );
    return;
  }

  // App-Dateien: Network-First (Updates sofort sichtbar, Offline-Fallback aus Cache)
  event.respondWith(
    fetch(event.request)
      .then(response => {
        if (!response || response.status !== 200 || response.type !== 'basic') {
          return response;
        }
        const toCache = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, toCache));
        return response;
      })
      .catch(() =>
        caches.match(event.request).then(cached =>
          cached || caches.match('/index.html')
        )
      )
  );
});
