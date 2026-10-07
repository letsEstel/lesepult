// Offline cache for the static site. Book data files are versioned (?v=hash) and cached forever;
// everything else is network-first with the cache as fallback, so updates show up on the next visit.
const CACHE = 'lesepult-1';
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => {
  const r = e.request;
  if (r.method !== 'GET') return;
  const u = new URL(r.url);
  const mine = u.origin === location.origin, fonts = /fonts\.(googleapis|gstatic)\.com$/.test(u.host);
  if (!mine && !fonts) return;
  if (mine && u.pathname.includes('/data/') && u.searchParams.has('v')) {
    e.respondWith(caches.open(CACHE).then(c => c.match(r).then(hit => hit || fetch(r).then(res => {
      if (res.ok) { const cp = res.clone(); c.keys().then(ks => ks.forEach(k => { const ku = new URL(k.url); if (ku.pathname === u.pathname && ku.search !== u.search) c.delete(k); })); c.put(r, cp); }
      return res;
    }))));
    return;
  }
  e.respondWith(fetch(r).then(res => {
    if (res.ok || res.type === 'opaque') { const cp = res.clone(); caches.open(CACHE).then(c => c.put(r, cp)); }
    return res;
  }).catch(() => caches.match(r, {ignoreSearch: r.mode === 'navigate'}).then(h => h || caches.match('./'))));
});
