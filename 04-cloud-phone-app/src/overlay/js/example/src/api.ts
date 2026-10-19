// The gateway's API as this page uses it: the viewer id of this page load
// and POSTs with the page token.
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
// the current one from the page itself (same origin only) and try once more.
export async function postFetch(url, init) {
  const response = await fetch(url, init);
  if (response.status !== 403) return response;
  const refused = await response.clone().json().catch(() => ({}));
  if (!String(refused.error ?? '').includes('page token')) return response;
  const page = await fetch(window.location.pathname, { cache: 'no-store' }).then((r) => r.text()).catch(() => '');
  const token = new DOMParser().parseFromString(page, 'text/html')
    .querySelector('meta[name="cloudphone-token"]')?.getAttribute('content');
  if (!token) return response;
  let meta = document.querySelector('meta[name="cloudphone-token"]');
  if (!meta) {
    meta = document.createElement('meta');
    meta.setAttribute('name', 'cloudphone-token');
    document.head.appendChild(meta);
  }
  meta.setAttribute('content', token);
  return fetch(url, { ...init, headers: { ...init.headers, 'X-CloudPhone-Token': token } });
}
