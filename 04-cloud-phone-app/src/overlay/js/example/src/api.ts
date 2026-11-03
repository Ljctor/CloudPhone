// The gateway's API as this page uses it: the viewer id of this page load
// and POSTs with the page token.
import { streamDiagnostic } from '../../src/components/emulator/net/stream_diagnostics';
import { setViewerId } from '../../src/components/emulator/net/ws_jsep_protocol_driver';

// One id per page load: lets this page disconnect the other viewers, and
// the gateway refuse this page after another one disconnected it.
export const VIEWER_ID = window.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
setViewerId(VIEWER_ID);

// The gateway writes a per-start token into the page; every POST carries it,
// so a page from another origin cannot drive Android.
export function postHeaders() {
  const token = document.querySelector('meta[name="cloudphone-token"]')?.getAttribute('content') ?? '';
  return { 'Content-Type': 'application/json', 'X-CloudPhone-Token': token };
}

// A POST with the page token. The token changes when the gateway restarts
// (a screen size or emulator change does that): on a token refusal, read
// the current one from the origin-guarded token endpoint and try once more.
let tokenRefresh = null;
async function refreshToken() {
  if (!tokenRefresh) {
    tokenRefresh = (async () => {
      const reply = await fetch('/api/v1/session/token', { cache: 'no-store', signal: AbortSignal.timeout(5000) });
      if (!reply.ok) throw new Error('Token refresh failed');
      const { token } = await reply.json();
      if (typeof token !== 'string' || !token || token.length > 256) throw new Error('Invalid token');
      let meta = document.querySelector('meta[name="cloudphone-token"]');
      if (!meta) {
        meta = document.createElement('meta');
        meta.setAttribute('name', 'cloudphone-token');
        document.head.appendChild(meta);
      }
      meta.setAttribute('content', token);
      streamDiagnostic('token-refreshed');
      return token;
    })().finally(() => { tokenRefresh = null; });
  }
  return tokenRefresh;
}

export async function postFetch(url, init) {
  const response = await fetch(url, init);
  if (response.status !== 403) return response;
  const refused = await response.clone().json().catch(() => ({}));
  if (!String(refused.error ?? '').includes('page token')) return response;
  streamDiagnostic('token-refused');
  try {
    const token = await refreshToken();
    if (init.signal?.aborted) return response;
    const headers = new Headers(init.headers);
    headers.set('X-CloudPhone-Token', token);
    return fetch(url, { ...init, headers });
  } catch {
    streamDiagnostic('token-refresh-failed');
    return response;
  }
}
