/**
 * Dynamic API base URL — resolves to the backend on the same host.
 * When accessed from localhost, uses localhost.
 * When accessed from a LAN IP (e.g. mobile on same network), uses that IP.
 * This allows the Mac to serve as a server for mobile clients.
 */
export function getApiBase(): string {
  if (typeof window === "undefined") {
    // SSR fallback
    return "http://127.0.0.1:7861";
  }
  // Use the same hostname the browser used to reach the frontend
  const host = window.location.hostname || "127.0.0.1";
  return `http://${host}:7861`;
}

/**
 * Whether the current client is accessing from the local machine.
 * Network (non-local) clients have restricted tool access.
 */
export function isLocalClient(): boolean {
  if (typeof window === "undefined") return true;
  const h = window.location.hostname;
  return h === "localhost" || h === "127.0.0.1" || h === "::1";
}

// ─── Auth token management ───
const AUTH_TOKEN_KEY = "kasset-auth-token";

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token: string) {
  if (typeof window !== "undefined") {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  }
}

export function clearAuthToken() {
  if (typeof window !== "undefined") {
    localStorage.removeItem(AUTH_TOKEN_KEY);
  }
}

/**
 * Fetch wrapper that attaches the auth token header for network clients.
 */
export function authFetch(url: string, init?: RequestInit): Promise<Response> {
  const token = getAuthToken();
  const headers = new Headers(init?.headers);
  if (token) {
    headers.set("x-auth-token", token);
  }
  return fetch(url, { ...init, headers });
}

/**
 * Install a global fetch interceptor that transparently adds the auth token
 * to all API requests. This avoids changing every fetch() call across the app.
 * Only targets requests to the backend (port 7861).
 */
if (typeof window !== "undefined") {
  const _originalFetch = window.fetch.bind(window);
  (window as any).fetch = function(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : (input as Request).url;
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    if (token && url.includes(":7861/api/")) {
      const headers = new Headers(init?.headers);
      if (!headers.has("x-auth-token")) {
        headers.set("x-auth-token", token);
      }
      return _originalFetch(input, { ...init, headers });
    }
    return _originalFetch(input, init);
  };
}
