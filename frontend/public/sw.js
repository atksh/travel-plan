const CACHE_NAME = "bosodrive-shell-v1";
const SHELL_ASSETS = ["/", "/manifest.json"];

function isNavigationRequest(request) {
  const acceptHeader = request.headers.get("accept") || "";
  return request.mode === "navigate" || acceptHeader.includes("text/html");
}

async function cacheSuccessfulResponse(request, response) {
  if (!response.ok) {
    return response;
  }
  const cache = await caches.open(CACHE_NAME);
  await cache.put(request, response.clone());
  return response;
}

async function handleNavigationRequest(request) {
  try {
    const networkResponse = await fetch(request);
    return await cacheSuccessfulResponse(request, networkResponse);
  } catch {
    const cachedResponse = await caches.match(request);
    return cachedResponse || caches.match("/");
  }
}

async function handleAssetRequest(request) {
  const cachedResponse = await caches.match(request);
  if (cachedResponse) {
    return cachedResponse;
  }
  const networkResponse = await fetch(request);
  return cacheSuccessfulResponse(request, networkResponse);
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS)),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key)),
      ),
    ),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") {
    return;
  }
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return;
  }
  if (isNavigationRequest(request)) {
    event.respondWith(handleNavigationRequest(request));
    return;
  }
  event.respondWith(handleAssetRequest(request));
});
