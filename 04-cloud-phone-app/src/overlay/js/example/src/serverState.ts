// The page's poll of GET /api/v1/state, the input of diagnose().
import { useEffect, useState } from 'react';
import { VIEWER_ID } from './api';

// Polls the gateway's view of the server: emulator service, Android boot,
// viewers, load. failures counts consecutive unanswered polls.
// details: also ask for the server metrics (CPU, memory, Android's frame
// rate), which cost the server an adb call: only while the server panel is
// open.
export function useServerState(gatewayUrl, details = false) {
  const [server, setServer] = useState({ value: null, failures: 0 });
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 4000);
      fetch(`${gatewayUrl}/api/v1/state?viewer=${encodeURIComponent(VIEWER_ID)}${details ? '&details=1' : ''}`,
        { cache: 'no-store', signal: controller.signal })
        .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
        .then((value) => { if (!cancelled) setServer({ value, failures: 0 }); })
        .catch(() => { if (!cancelled) setServer((current) => ({ ...current, failures: current.failures + 1 })); })
        .finally(() => window.clearTimeout(timeout));
    };
    load();
    const timer = window.setInterval(load, details ? 2000 : 3000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [gatewayUrl, details]);
  return server;
}
