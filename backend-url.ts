const LOCAL_BACKEND_URL = 'http://127.0.0.1:8000';

function cleanUrl(value: string) {
  return value.replace(/\/+$/, '');
}

/** Where the Next.js server proxies /api/backend/* to. Set BACKEND_URL when
 * the FastAPI service runs anywhere other than this machine on port 8000. */
export function getBackendBaseUrl() {
  const explicitUrl = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL;
  return explicitUrl ? cleanUrl(explicitUrl) : LOCAL_BACKEND_URL;
}
