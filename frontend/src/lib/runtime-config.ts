function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}

export function getApiBase(): string {
  return requireEnv("NEXT_PUBLIC_API_URL");
}

export function getGoogleMapsApiKey(): string {
  return requireEnv("NEXT_PUBLIC_GOOGLE_MAPS_API_KEY");
}
