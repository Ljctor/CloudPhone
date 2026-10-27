// Persist a small, explicitly selected subset of browser diagnostics. No SDP,
// addresses, typed keys or exception text leave the browser.
import { onStreamDiagnostic, streamDiagnostic } from '../../src/components/emulator/net/stream_diagnostics';
import { postFetch, postHeaders } from './api';

const sessions = new Map();
let pending = [];
let sending = false;
let lastUploadStatus = null;

const states = {
  'peer-state': 'connection', 'ice-state': 'ice', 'ice-gathering': 'gathering',
  'signaling-state': 'signalling',
};
const wakes = {
  AudioVolumeUp: 'volume-up', AudioVolumeDown: 'volume-down', AudioVolumeMute: 'volume-mute',
  Power: 'power', WakeUp: 'wake',
};

function eventFor({ event, data }) {
  if (states[event]) return { kind: states[event], state: data.state };
  if (event === 'track') return { kind: 'track', state: data.kind };
  if (event.startsWith('track-')) return { kind: 'track', state: event.slice(6) };
  if (event === 'first-frame') return { kind: 'frame', state: event, elapsedMs: data.elapsedMs };
  if (event === 'first-frame-timeout') return { kind: 'error', state: event, elapsedMs: data.elapsedMs };
  if (event === 'play-resolved' || event === 'play-rejected') {
    return { kind: 'playback', state: event.slice(5) };
  }
  if (event === 'hardware-key') return { kind: 'wake', state: wakes[data.key] };
  if (event === 'page-visibility') return { kind: 'wake', state: data.state };
  if (event === 'page-focus' || event === 'page-blur') return { kind: 'wake', state: event.slice(5) };
  if (event === 'presentation-stalled' || event === 'presentation-resumed') {
    return { kind: 'playback', state: event };
  }
  if (event === 'stats') {
    const selected = { kind: 'stats' };
    for (const key of ['framesDecoded', 'bytesReceived', 'packetsLost', 'framesReceived',
      'presented', 'keyFramesDecoded', 'freezeCount', 'totalFreezesDuration']) {
      if (Number.isFinite(data[key])) selected[key] = data[key];
    }
    return selected;
  }
  return null;
}

onStreamDiagnostic((record) => {
  if (record.event === 'gateway-session') {
    sessions.set(record.session, record.data.sessionId);
    if (sessions.size > 20) sessions.delete(sessions.keys().next().value);
    return;
  }
  const event = eventFor(record);
  const sessionId = sessions.get(record.session);
  if (!event || !sessionId) return;
  pending.push({ sessionId, event, attempts: 0 });
  if (pending.length > 100) pending.shift();
});

async function flush() {
  if (sending || !pending.length) return;
  const sessionId = pending[0].sessionId;
  const batch = pending.filter((item) => item.sessionId === sessionId).slice(0, 20);
  pending = pending.filter((item) => !batch.includes(item));
  sending = true;
  const retry = () => {
    const retried = batch.filter((item) => item.attempts < 2)
      .map((item) => ({ ...item, attempts: item.attempts + 1 }));
    pending = [...retried, ...pending].slice(-100);
  };
  const reportStatus = (status) => {
    if (status === lastUploadStatus) return;
    lastUploadStatus = status;
    streamDiagnostic('telemetry-upload-status', { status });
  };
  try {
    // Best effort: a failed diagnostics request must never disturb the stream
    // or create recursive log traffic. The local trace remains available.
    const response = await postFetch('/api/v1/stream-diagnostics/events', {
      method: 'POST', headers: postHeaders(), keepalive: true,
      body: JSON.stringify({ sessionId, events: batch.map((item) => item.event) }),
      signal: AbortSignal.timeout(5000),
    });
    reportStatus(response.status);
    if (response.status === 429 || response.status >= 500) retry();
  } catch {
    reportStatus(0);
    retry();
  }
  finally { sending = false; }
}

window.setInterval(flush, 2000);
window.addEventListener('pagehide', flush);
