const apiBase = process.env.NEXT_PUBLIC_API_URL;
if (!apiBase) {
  throw new Error("NEXT_PUBLIC_API_URL is required");
}

const googleMapsApiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
if (!googleMapsApiKey) {
  throw new Error("NEXT_PUBLIC_GOOGLE_MAPS_API_KEY is required");
}

export const API_BASE = apiBase;
export const GOOGLE_MAPS_API_KEY = googleMapsApiKey;
