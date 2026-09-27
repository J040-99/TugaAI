/* TugaAI service worker — PWA instalável (mobile) */
const CACHE_NAME = 'tugaai-v2';
const PRECACHE = ['/', '/manifest.json'];

self.addEventListener('install', (event) => {
	event.waitUntil(
		caches
			.open(CACHE_NAME)
			.then((cache) => cache.addAll(PRECACHE))
			.then(() => self.skipWaiting())
	);
});

self.addEventListener('activate', (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((keys) =>
				Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
			)
			.then(() => self.clients.claim())
	);
});

self.addEventListener('message', (event) => {
	if (event.data === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
	const { request } = event;

	if (
		request.method !== 'GET' ||
		request.url.includes('/api/') ||
		request.url.includes('/ws') ||
		request.url.includes('/auth')
	) {
		return;
	}

	// JS/CSS e HTML: SEMPRE rede primeiro (evita menu/UI antigo em cache)
	const url = new URL(request.url);
	const isHashedAsset =
		/\.(js|css)$/.test(url.pathname) || url.pathname.includes('/_app/immutable/');

	if (request.mode === 'navigate' || isHashedAsset) {
		event.respondWith(
			fetch(request)
				.then((response) => {
					if (response.ok && response.type === 'basic') {
						const copy = response.clone();
						caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
					}
					return response;
				})
				.catch(() => caches.match(request))
		);
		return;
	}

	// Resto de estáticos (imagens, fontes): cache primeiro
	event.respondWith(
		caches.match(request).then(
			(cached) =>
				cached ||
				fetch(request).then((response) => {
					if (response.ok && response.type === 'basic') {
						const copy = response.clone();
						caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
					}
					return response;
				})
		)
	);
});
