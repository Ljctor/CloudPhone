// Bounded, address-free browser trace. No SDP, ICE addresses, input text or tokens.
// Inspect/copy with window.cloudphoneDiagnostics.snapshot() in browser tools.
type Fields = Record<string, string | number | boolean | null>;
const records: { time: number; session: number; event: string; data: Fields }[] = [];
const listeners = new Set<(record: typeof records[number]) => void>();
let session = 0;

export function streamDiagnostic(event: string, data: Fields = {}, id = session) {
  const record = { time: Date.now() / 1000, session: id, event, data };
  records.push(record);
  if (records.length > 250) records.shift();
  listeners.forEach((listener) => listener(record));
}

export function beginStreamDiagnostic() {
  session += 1;
  streamDiagnostic('session-start', { visibility: document.visibilityState });
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
