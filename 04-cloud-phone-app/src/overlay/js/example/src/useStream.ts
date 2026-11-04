// The Android stream's life: its state, remounting it to reconnect (the
// toolbar's button, Android usable again, the page shown again), the
// feedback while a manual reconnect waits for its first frame, and how long
// it has been connecting. When to reconnect is in streamRules.ts.
import { useEffect, useRef, useState } from 'react';
import { activePeerConnection, disconnectActiveStream } from '../../src/components/emulator/net/ws_jsep_protocol_driver';
import { postFetch, postHeaders, VIEWER_ID } from './api';
import { english } from './i18n';
import { pageLog } from './logs';
import { streamDiagnostic } from '../../src/components/emulator/net/stream_diagnostics';
import { MEDIA_RECONNECT_COOLDOWN_MS } from './streamHealth';
import {
  AUTO_RECONNECT_DELAY_MS, RECONNECT_FEEDBACK_MS, REMOUNT_DELAY_MS, STUCK_AFTER_S,
  autoReconnectDue, secondsSince, serverHealthy, streamStateLine,
} from './streamRules';

// server: useServerState()'s; input: useInput()'s (a reconnect ends the
// touch in progress). Returns { state, mounted, generation (the stream's
// key), reconnecting, connectingFor (s), manualReconnect, handleState }.
export function useStream({ server, input }) {
  const alive = useRef(true);
  const acceptingState = useRef(true);
  const currentGeneration = useRef(0);
  const resetAbort = useRef(null);
  const mediaReconnectAt = useRef(-Infinity);
  const feedbackTimer = useRef(null);
  const reconnectTimer = useRef(null);
  const [reconnecting, setReconnecting] = useState(false);
  const [state, setState] = useState('connecting');
  const latestState = useRef(state);
  latestState.current = state;
  const [visible, setVisible] = useState(document.visibilityState !== 'hidden');
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

  const reconnectStream = async () => {
    if (!acceptingState.current) return;
    acceptingState.current = false;
    input.pointerDown.current = false;
    disconnectActiveStream();
    latestState.current = 'connecting';
    setState('connecting');
    setConnectingFor(0);
    setMounted(false);
    streamDiagnostic('reset-requested');
    const controller = new AbortController();
    resetAbort.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 30000);
    let resetComplete = false;
    try {
      const response = await postFetch('/api/v1/stream/reset', {
        method: 'POST', headers: postHeaders(), body: JSON.stringify({ viewer: VIEWER_ID }), signal: controller.signal,
      });
      resetComplete = response.ok;
      streamDiagnostic(response.ok ? 'reset-completed' : 'reset-failed');
    } catch {
      if (alive.current) streamDiagnostic('reset-failed');
    } finally {
      window.clearTimeout(timeout);
      resetAbort.current = null;
    }
    if (!alive.current) return;
    if (!resetComplete) {
      currentGeneration.current += 1;
      setGeneration(currentGeneration.current);
      acceptingState.current = true;
      latestState.current = 'disconnected';
      setState('disconnected');
      stopFeedback();
      return;
    }
    reconnectTimer.current = window.setTimeout(() => {
      currentGeneration.current += 1;
      setGeneration(currentGeneration.current);
      acceptingState.current = true;
      setMounted(true);
      reconnectTimer.current = null;
    }, REMOUNT_DELAY_MS);
  };

  const loggedState = useRef(null);
  const handleState = (nextState, fromGeneration = currentGeneration.current) => {
    if (!alive.current || !acceptingState.current || fromGeneration !== currentGeneration.current) return;
    // The stream reports its state often; only changes are logged.
    if (nextState !== loggedState.current) {
      loggedState.current = nextState;
      const [text, values] = streamStateLine(nextState);
      pageLog('normal', english(text, values));
    }
    latestState.current = nextState;
    setState(nextState);
    if (nextState === 'connected' && reconnectTimer.current === null) stopFeedback();
  };

  const handleError = (_error, fromGeneration = currentGeneration.current) => {
    if (!alive.current || !acceptingState.current || fromGeneration !== currentGeneration.current) return;
    streamDiagnostic('signaling-error');
    pageLog('warning', 'Stream signaling or playback error; see stream diagnostics.');
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

  const healthy = server.connection === 'reachable' && !server.stateError && serverHealthy(server) && !server.value?.kicked;
  const latestHealthy = useRef(healthy);
  latestHealthy.current = healthy;
  const recoverMediaStall = ({ connection, generation: fromGeneration, evidence }) => {
    if (!alive.current || !acceptingState.current || document.hidden
        || !latestHealthy.current || latestState.current !== 'connected'
        || fromGeneration !== currentGeneration.current || connection !== activePeerConnection()
        || performance.now() - mediaReconnectAt.current < MEDIA_RECONNECT_COOLDOWN_MS) return;
    mediaReconnectAt.current = performance.now();
    streamDiagnostic('media-stall-reconnect', evidence);
    // Existing reset is scoped to VIEWER_ID; never restart Android or reset
    // another viewer. Generation/connection checks reject stale async stats.
    reconnectStream();
  };
  useEffect(() => {
    if (!visible || !autoReconnectDue({ healthy, stream: state, connectingFor })) return undefined;
    const timer = window.setTimeout(reconnectStream, AUTO_RECONNECT_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [healthy, visible, state, connectingFor >= STUCK_AFTER_S]);

  useEffect(() => {
    alive.current = true;
    let wasHidden = document.visibilityState === 'hidden';

    const visibilityChanged = () => {
      streamDiagnostic('page-visibility', { state: document.visibilityState });
      setVisible(document.visibilityState !== 'hidden');
      if (document.visibilityState === 'hidden') {
        wasHidden = true;
      } else if (wasHidden) {
        wasHidden = false;
        // Returning to the page does not invalidate a decoded live stream.
        if (latestHealthy.current && !['connected', 'blocked'].includes(latestState.current)) reconnectStream();
      }
    };

    const pageShown = (event) => {
      streamDiagnostic('page-shown', { persisted: event.persisted });
      if (event.persisted && latestHealthy.current && !['connected', 'blocked'].includes(latestState.current)) reconnectStream();
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
      alive.current = false;
      resetAbort.current?.abort();
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

  return { state, mounted, generation, reconnecting, connectingFor, manualReconnect, handleState, handleError, recoverMediaStall };
}
