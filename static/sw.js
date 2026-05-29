const CACHE_NAME = 'kasirinaja-cache-v1';
const urlsToCache = [
  '/'
];

// Install Service Worker
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        return cache.addAll(urlsToCache);
      })
  );
});

// Intercept Fetch Requests (Syarat utama PWA)
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // Kembalikan cache jika ada, jika tidak ambil dari internet
        return response || fetch(event.request);
      })
  );
});