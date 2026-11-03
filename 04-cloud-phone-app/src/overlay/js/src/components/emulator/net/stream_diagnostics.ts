// Bounded, address-free browser trace. No SDP, ICE addresses, input text or tokens.
// Inspect/copy with window.cloudphoneDiagnostics.snapshot() in browser tools.
type Fields = Record<string, string | number | boolean | null>;
const records: { time: number; session: number; event: string; data: Fields }[] = [];
const listeners = new Set<(record: typeof records[number]) => void>();
let session = 0;
const attempts = new Map<number, string>();
export function diagnosticAttempt(id = session): string | undefined { return attempts.get(id); }

export function streamDiagnostic(event: string, data: Fields = {}, id = session) {
  const record = { time: Date.now() / 1000, session: id, event, data };
  records.push(record);
  if (records.length > 250) records.shift();
  listeners.forEach((listener) => listener(record));
}

export function beginStreamDiagnostic() {
  session += 1;
  const attemptId = window.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  attempts.set(session, attemptId);
  if (attempts.size > 32) attempts.delete(attempts.keys().next().value);
  let localStorageKeys = 0, sessionStorageKeys = 0, storageAvailable = true;
  try { localStorageKeys = Math.min(localStorage.length, 1000); sessionStorageKeys = Math.min(sessionStorage.length, 1000); }
  catch { storageAvailable = false; }
  streamDiagnostic('session-start', { visibility: document.visibilityState, localStorageKeys,
    sessionStorageKeys, storageAvailable, tokenPresent: !!document.querySelector('meta[name="cloudphone-token"]')?.getAttribute('content'),
    secureContext: window.isSecureContext, online: navigator.onLine });
  return session;
}

export function onStreamDiagnostic(listener: (record: typeof records[number]) => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

if (typeof window !== 'undefined') {
  (window as any).cloudphoneDiagnostics = {
    snapshot: () => JSON.parse(JSON.stringify({ version: 1, records })),
  };
}
