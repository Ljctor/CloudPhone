// The Android stream's life: its state, remounting it to reconnect (the
// toolbar's button, Android usable again, the page shown again), the
// feedback while a manual reconnect waits for its first frame, and how long
// it has been connecting. When to reconnect is in streamRules.ts.
import { useEffect, useRef, useState } from 'react';
import { english } from './i18n';
import { pageLog } from './logs';
import { streamDiagnostic } from '../../src/components/emulator/net/stream_diagnostics';
import {
  AUTO_RECONNECT_DELAY_MS, RECONNECT_FEEDBACK_MS, REMOUNT_DELAY_MS, STUCK_AFTER_S,
  autoReconnectDue, secondsSince, serverHealthy, streamStateLine,
} from './streamRules';

// server: useServerState()'s; input: useInput()'s (a reconnect ends the
// touch in progress). Returns { state, mounted, generation (the stream's
// key), reconnecting, connectingFor (s), manualReconnect, handleState }.
export function useStream({ server, input }) {
  const feedbackTimer = useRef(null);
  const reconnectTimer = useRef(null);
  const [reconnecting, setReconnecting] = useState(false);
  const [state, setState] = useState('connecting');
  const [mounted, setMounted] = useState(true);
  const [generation, setGeneration] = useState(0);
  const [connectingFor, setConnectingFor] = useState(0);

  const stopFeedback = () => {
    setReconnecting(false);
    if (feedbackTimer.current !== null) {
      window.clearTimeout(feedbackTimer.current);
      feedbackTimer.current = null;
    }
  };

  // Manual refresh: show that the click was taken into account until the new
  // stream displays its first frame.
  const manualReconnect = () => {
    streamDiagnostic('manual-reconnect');
    // Disconnected by another viewer: a new page load is a new viewer.
    if (server.value?.kicked) {
      window.location.reload();
      return;
    }
    setReconnecting(true);
    if (feedbackTimer.current !== null) window.clearTimeout(feedbackTimer.current);
    feedbackTimer.current = window.setTimeout(stopFeedback, RECONNECT_FEEDBACK_MS);
    reconnectStream();
  };

  const reconnectStream = () => {
    if (reconnectTimer.current !== null) return;
    input.pointerDown.current = false;
    setState('connecting');
    setMounted(false);
    reconnectTimer.current = window.setTimeout(() => {
      setGeneration((current) => current + 1);
      setMounted(true);
      reconnectTimer.current = null;
    }, REMOUNT_DELAY_MS);
  };

  const loggedState = useRef(null);
  const handleState = (nextState) => {
    // The stream reports its state often; only changes are logged.
    if (nextState !== loggedState.current) {
      loggedState.current = nextState;
      const [text, values] = streamStateLine(nextState);
      pageLog('normal', english(text, values));
    }
    setState(nextState);
    if (nextState === 'connected' && reconnectTimer.current === null) stopFeedback();
  };

  useEffect(() => {
    if (state === 'connected') {
      setConnectingFor(0);
      return undefined;
    }
    const started = Date.now();
    const timer = window.setInterval(() => setConnectingFor(secondsSince(started, Date.now())), 1000);
    return () => window.clearInterval(timer);
  }, [state, generation]);

  const healthy = serverHealthy(server);
  useEffect(() => {
    if (!autoReconnectDue({ healthy, stream: state, connectingFor })) return undefined;
    const timer = window.setTimeout(reconnectStream, AUTO_RECONNECT_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [healthy, state, connectingFor >= STUCK_AFTER_S]);

  useEffect(() => {
    let wasHidden = document.visibilityState === 'hidden';

    const visibilityChanged = () => {
      streamDiagnostic('page-visibility', { state: document.visibilityState });
      if (document.visibilityState === 'hidden') {
        wasHidden = true;
      } else if (wasHidden) {
        wasHidden = false;
        reconnectStream();
      }
    };

    const pageShown = (event) => {
      streamDiagnostic('page-shown', { persisted: event.persisted });
      if (event.persisted) reconnectStream();
    };

    const focusChanged = (event) => streamDiagnostic(`page-${event.type}`);
    // Hardware volume keys are not exposed on every mobile browser. Record
    // only known volume/wake names; never capture typed text or other keys.
    const hardwareKey = (event) => {
      if (['AudioVolumeUp', 'AudioVolumeDown', 'AudioVolumeMute', 'WakeUp', 'Power'].includes(event.key)) {
        streamDiagnostic('hardware-key', { key: event.key, trusted: event.isTrusted });
      }
    };
    window.addEventListener('keydown', hardwareKey, true);
    window.addEventListener('focus', focusChanged);
    window.addEventListener('blur', focusChanged);
    document.addEventListener('visibilitychange', visibilityChanged);
    window.addEventListener('pageshow', pageShown);
    return () => {
      window.removeEventListener('keydown', hardwareKey, true);
      window.removeEventListener('focus', focusChanged);
      window.removeEventListener('blur', focusChanged);
      document.removeEventListener('visibilitychange', visibilityChanged);
      window.removeEventListener('pageshow', pageShown);
      if (reconnectTimer.current !== null) {
        window.clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
      if (feedbackTimer.current !== null) {
        window.clearTimeout(feedbackTimer.current);
        feedbackTimer.current = null;
      }
    };
  }, []);

  return { state, mounted, generation, reconnecting, connectingFor, manualReconnect, handleState };
}
