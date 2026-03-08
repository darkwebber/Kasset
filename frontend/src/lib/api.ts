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
 * Callback invoked when a 401 is detected on an API response.
 * Set by page.tsx to trigger the auth modal without a hard reload.
 */
let _onSessionExpired: (() => void) | null = null;

export function onSessionExpired(cb: () => void) {
  _onSessionExpired = cb;
}

/**
 * Install a global fetch interceptor that transparently adds the auth token
 * to all API requests. This avoids changing every fetch() call across the app.
 * Only targets requests to the backend (port 7861).
 * Also intercepts 401 responses to trigger re-authentication for network clients.
 */
if (typeof window !== "undefined") {
  const _originalFetch = window.fetch.bind(window);
  (window as any).fetch = function(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : (input as Request).url;
    const isApiCall = url.includes(":7861/api/");
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    let fetchPromise: Promise<Response>;
    if (token && isApiCall) {
      const headers = new Headers(init?.headers);
      if (!headers.has("x-auth-token")) {
        headers.set("x-auth-token", token);
      }
      fetchPromise = _originalFetch(input, { ...init, headers });
    } else {
      fetchPromise = _originalFetch(input, init);
    }
    // Intercept 401s on API calls — session expired or revoked
    if (isApiCall && !url.includes("/api/auth/")) {
      fetchPromise = fetchPromise.then(response => {
        if (response.status === 401 && _onSessionExpired) {
          clearAuthToken();
          _onSessionExpired();
        }
        return response;
      });
    }
    return fetchPromise;
  };
}
