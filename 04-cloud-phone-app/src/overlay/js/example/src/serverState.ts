// The page's poll of GET /api/v1/state, the input of diagnose().
import { useEffect, useState } from 'react';
import { VIEWER_ID } from './api';

// Polls the gateway's view of the server: emulator service, Android boot,
// viewers, load. failures counts consecutive unanswered polls.
// details: also ask for the server metrics (CPU, memory, Android's frame
// rate), which cost the server an adb call: only while the server panel is
// open.
export function useServerState(gatewayUrl, details = false) {
  const [server, setServer] = useState({ value: null, failures: 0, connection: 'checking', stateError: false });
  useEffect(() => {
    let cancelled = false;
    let timer = null;
    let active = null;
    const interval = details ? 2000 : 3000;
    const load = async () => {
      if (cancelled) return;
      const started = Date.now();
      const controller = new AbortController();
      active = controller;
      const timeout = window.setTimeout(() => controller.abort(), 4000);
      try {
        const response = await fetch(`${gatewayUrl}/api/v1/state?viewer=${encodeURIComponent(VIEWER_ID)}${details ? '&details=1' : ''}`,
          { cache: 'no-store', signal: controller.signal });
        if (!response.ok) throw new Error(String(response.status));
        const value = await response.json();
        if (controller.signal.aborted) throw new Error('State request timed out');
        if (!cancelled) setServer({ value, failures: 0, connection: 'reachable', stateError: false });
      } catch {
        window.clearTimeout(timeout);
        if (cancelled) return;
        // A slow/broken state provider is not proof that the gateway itself
        // is offline. Check its cheap HTTP endpoint before classifying it.
        const probe = new AbortController();
        active = probe;
        const probeTimeout = window.setTimeout(() => probe.abort(), 1000);
        let reachable = false;
        try {
          const response = await fetch(`${gatewayUrl}/api/v1/ping`, { cache: 'no-store', signal: probe.signal });
          reachable = response.ok && !probe.signal.aborted;
        } catch { /* A failed probe is a failed connection observation. */ }
        finally { window.clearTimeout(probeTimeout); }
        if (!cancelled) setServer((current) => ({ ...current, failures: current.failures + 1,
          connection: reachable ? 'reachable' : 'unreachable', stateError: true }));
      } finally {
        window.clearTimeout(timeout);
        active = null;
        // Never let an older request race a newer result. Slow requests
        // consume the interval instead of piling up overlapping polls.
        if (!cancelled) timer = window.setTimeout(load, Math.max(0, interval - (Date.now() - started)));
      }
    };
    load();
    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
      active?.abort();
    };
  }, [gatewayUrl, details]);
  return server;
}
