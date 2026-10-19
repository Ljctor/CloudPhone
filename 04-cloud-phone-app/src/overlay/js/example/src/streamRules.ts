// When the page reconnects the Android stream, and what it logs of the
// stream's state. No React, no DOM.

// Give up showing the reconnect feedback if no frame arrives in this time.
export const RECONNECT_FEEDBACK_MS = 15000;
// Leave enough time for the WebSocket bye to reach the gateway and for the
// emulator-side participant to be destroyed before requesting a new one.
export const REMOUNT_DELAY_MS = 1000;
// A stream still connecting after this many seconds counts as lost.
export const STUCK_AFTER_S = 20;
// Wait this long once a reconnect is due, in case the stream recovers.
export const AUTO_RECONNECT_DELAY_MS = 2000;

// Android is usable: the gateway answers, Android has booted and the
// emulator is not starting.
export function serverHealthy(server) {
  return server.failures < 2 && server.value?.android?.booted === true
    && server.value?.emulator?.active !== 'activating';
}

// Android is usable again (after a crash, a restart or a lost stream) and
// the video is cut or stuck: reconnect it without waiting for the user.
export function autoReconnectDue({ healthy, stream, connectingFor }) {
  if (!healthy || stream === 'connected') return false;
  return stream === 'disconnected' || connectingFor >= STUCK_AFTER_S;
}

// Whole seconds from started to now (milliseconds).
export function secondsSince(started, now) {
  return Math.floor((now - started) / 1000);
}

// The log line for a new stream state: [French source text, values].
export function streamStateLine(state) {
  const said = { connected: 'Vidéo connectée', connecting: 'Vidéo en connexion…', disconnected: 'Vidéo coupée' }[state];
  return said ? [said] : ['Vidéo : {state}', { state }];
}
