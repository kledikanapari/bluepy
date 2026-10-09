// Bump when precache.json changes so installed apps download the new files.
const CACHE_NAME = "ear-web-v2";

// Device pages are opened as /MainControl_<name> (rewritten by the server to
// /MainControl/MainControl_<name>.html); do the same mapping when offline.
function cacheKeyFor(url) {
    if (url.pathname === "/" || url.pathname === "") {
        return "/index.html";
    }
    const rewrite = url.pathname.match(/^\/(MainControl_[A-Za-z0-9_]+)(\.html)?$/);
    if (rewrite) {
        return "/MainControl/" + rewrite[1] + ".html";
    }
    return url.pathname;
}

// Download every file of the app so it keeps working when no server is running.
// Failures are tolerated: a missing file is fetched again the next time it is used.
async function precacheAll() {
    const cache = await caches.open(CACHE_NAME);
    let urls;
    try {
        const response = await fetch("/precache.json", { cache: "no-store" });
        urls = await response.json();
    } catch (error) {
        console.error("Precache list unavailable:", error);
        return;
    }
    const BATCH = 8;
    for (let i = 0; i < urls.length; i += BATCH) {
        await Promise.all(urls.slice(i, i + BATCH).map(async (url) => {
            if (await cache.match(url)) {
                return;
            }
            try {
                const response = await fetch(url, { cache: "no-store" });
                if (response.ok) {
                    await cache.put(url, response);
                }
            } catch (error) {
                console.warn("Precache failed for " + url, error);
            }
        }));
    }
}

self.addEventListener("install", (event) => {
    self.skipWaiting();
    event.waitUntil(precacheAll());
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((names) => {
            return Promise.all(
                names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))
            );
        }).then(() => self.clients.claim())
    );
});

// Network first (so updates show up while the server runs), cache when offline.
self.addEventListener("fetch", (event) => {
    const request = event.request;
    const url = new URL(request.url);
    if (request.method !== "GET" || url.origin !== self.location.origin) {
        return;
    }
    const key = cacheKeyFor(url);

    event.respondWith(
        fetch(request)
            .then((response) => {
                if (response && response.ok) {
                    const responseClone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(key, responseClone));
                    return response;
                }
                return caches.match(key).then((cached) => cached || response);
            })
            .catch(() => caches.match(key).then((cached) => cached || Response.error()))
    );
});
