import { readFile } from "node:fs/promises";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { describe, expect, it, vi } from "vitest";

const CACHE_NAME = "bosodrive-shell-v1";
const ORIGIN = "https://example.com";
const SW_PATH = fileURLToPath(new URL("../../public/sw.js", import.meta.url));

type FetchHandler = ReturnType<typeof vi.fn>;
type WorkerListener = (event: {
  request?: Request;
  waitUntil: (promise: Promise<unknown>) => void;
  respondWith: (promise: Promise<Response>) => void;
}) => void;

function keyFor(input: RequestInfo | URL): string {
  if (typeof input === "string") {
    return new URL(input, ORIGIN).toString();
  }
  if (input instanceof URL) {
    return input.toString();
  }
  return input.url;
}

async function createServiceWorkerHarness(fetchImpl: FetchHandler) {
  const listeners = new Map<string, WorkerListener>();
  const stores = new Map<string, Map<string, Response>>();

  const cachesApi = {
    async open(name: string) {
      let store = stores.get(name);
      if (!store) {
        store = new Map<string, Response>();
        stores.set(name, store);
      }
      return {
        addAll: async (urls: string[]) => {
          for (const url of urls) {
            store.set(
              keyFor(url),
              new Response(`precache:${url}`, { status: 200 }),
            );
          }
        },
        match: async (input: RequestInfo | URL) => {
          const response = store.get(keyFor(input));
          return response ? response.clone() : undefined;
        },
        put: async (input: RequestInfo | URL, response: Response) => {
          store.set(keyFor(input), response.clone());
        },
      };
    },
    async match(input: RequestInfo | URL) {
      for (const store of stores.values()) {
        const response = store.get(keyFor(input));
        if (response) {
          return response.clone();
        }
      }
      return undefined;
    },
    async keys() {
      return [...stores.keys()];
    },
    async delete(name: string) {
      return stores.delete(name);
    },
  };

  const context = {
    self: {
      location: { origin: ORIGIN },
      addEventListener: (type: string, listener: WorkerListener) => {
        listeners.set(type, listener);
      },
    },
    caches: cachesApi,
    fetch: fetchImpl,
    URL,
    Request,
    Response,
    Headers,
    Promise,
    console,
  };

  const source = await readFile(SW_PATH, "utf8");
  vm.runInNewContext(source, context, { filename: SW_PATH });

  async function dispatchInstall() {
    const waitUntilPromises: Promise<unknown>[] = [];
    const listener = listeners.get("install");
    if (!listener) {
      throw new Error("Missing install listener");
    }
    listener({
      waitUntil: (promise) => waitUntilPromises.push(promise),
      respondWith: () => {
        throw new Error("install should not call respondWith");
      },
    });
    await Promise.all(waitUntilPromises);
  }

  async function dispatchFetch(request: Request) {
    let responsePromise: Promise<Response> | undefined;
    const listener = listeners.get("fetch");
    if (!listener) {
      throw new Error("Missing fetch listener");
    }
    listener({
      request,
      waitUntil: () => {},
      respondWith: (promise) => {
        responsePromise = promise;
      },
    });
    if (!responsePromise) {
      throw new Error("fetch handler did not call respondWith");
    }
    return responsePromise;
  }

  return {
    caches: cachesApi,
    dispatchInstall,
    dispatchFetch,
  };
}

describe("service worker navigation caching", () => {
  it("uses network-first for navigation requests and refreshes the cached page", async () => {
    const fetchMock = vi.fn(async () => new Response("fresh page", { status: 200 }));
    const worker = await createServiceWorkerHarness(fetchMock);
    await worker.dispatchInstall();

    const cache = await worker.caches.open(CACHE_NAME);
    const request = new Request(`${ORIGIN}/trips/42`, {
      headers: { accept: "text/html" },
    });
    await cache.put(request, new Response("stale page", { status: 200 }));

    const response = await worker.dispatchFetch(request);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(await response.text()).toBe("fresh page");
    expect(await (await worker.caches.match(request))?.text()).toBe("fresh page");
  });

  it("falls back to the cached shell when a navigation request is offline", async () => {
    const fetchMock = vi.fn(async () => {
      throw new Error("offline");
    });
    const worker = await createServiceWorkerHarness(fetchMock);
    await worker.dispatchInstall();

    const response = await worker.dispatchFetch(
      new Request(`${ORIGIN}/trips/42`, {
        headers: { accept: "text/html" },
      }),
    );

    expect(await response.text()).toBe("precache:/");
  });

  it("keeps cache-first behavior for same-origin assets", async () => {
    const fetchMock = vi.fn(async () => new Response("network asset", { status: 200 }));
    const worker = await createServiceWorkerHarness(fetchMock);
    await worker.dispatchInstall();

    const request = new Request(`${ORIGIN}/app.js`, {
      headers: { accept: "application/javascript" },
    });
    const cache = await worker.caches.open(CACHE_NAME);
    await cache.put(request, new Response("cached asset", { status: 200 }));

    const response = await worker.dispatchFetch(request);

    expect(fetchMock).not.toHaveBeenCalled();
    expect(await response.text()).toBe("cached asset");
  });
});
