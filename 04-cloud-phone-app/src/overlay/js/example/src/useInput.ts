// Touches and keys from the page to Android: over the emulator's WebRTC
// data channels when open, otherwise through the gateway. The mapping and
// the queue's rules are in touchInput.ts.
import { useRef, useState } from 'react';
import { sendInputEvent } from '../../src/components/emulator/net/ws_jsep_protocol_driver';
import Proto from '../../src/proto/emulator_controller_pb';
import { tr } from './i18n';
import { emitTap } from './plugins';
import { postFetch, postHeaders } from './api';
import { pageLog } from './logs';
import { enqueue, queueIdle, takeNext, tapOf, touchPoint, touchQueue } from './touchInput';

// Touches and keys go over the emulator's own WebRTC data channels ("touch",
// "keyboard"): no HTTP request, no gRPC hop. HTTP through the gateway stays
// as the fallback while no channel is open. See docs/DEVELOPMENT.md.
const USE_DATA_CHANNEL = true;

// display: Android's screen size; showMarker: the setting that shows the
// local marker under the finger.
// Returns the handlers for the touch surface, sendKey, the marker's ref,
// pointerDown (a reconnect clears it), inputPath ("data channel" or "HTTP":
// how the last touch reached Android) and touchFailures (consecutive failed
// requests, for diagnose()).
export function useInput({ gatewayUrl, display, showMarker: markerShown }) {
  const pointerDown = useRef(false);
  const touchSender = useRef(touchQueue());
  const touchMarker = useRef(null);
  // Where and when the current touch started, for plugins' onTap.
  const touchStart = useRef(null);
  const inputPath = useRef('–');
  const [touchFailures, setTouchFailures] = useState(0);

  const post = (path, body) => postFetch(`${gatewayUrl}${path}`, {
    method: 'POST',
    headers: postHeaders(),
    body: JSON.stringify(body),
  }).then((response) => {
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    setTouchFailures(0);
  }).catch((error) => {
    setTouchFailures((count) => count + 1);
    console.error('Android control:', error);
  });

  // Keys: the emulator's "keyboard" data channel when open (a keypress with
  // the DOM key name), otherwise the gateway, which uses adb.
  const sendKey = (key) => {
    if (USE_DATA_CHANNEL) {
      const event = new Proto.KeyboardEvent();
      event.setEventtype(Proto.KeyboardEvent.KeyEventType.KEYPRESS);
      event.setKey(key);
      if (sendInputEvent('keyboard', event)) return;
    }
    post('/api/v1/emulator/key', { key });
  };

  const touchCoordinates = (event) => touchPoint(event.clientX, event.clientY,
    event.currentTarget.getBoundingClientRect(), display);

  const pumpTouches = () => {
    const sender = touchSender.current;
    const next = takeNext(sender);
    if (!next) return;
    sender.inFlight = true;
    post('/api/v1/emulator/touch', next).finally(() => {
      sender.inFlight = false;
      pumpTouches();
    });
  };

  // Preferred path: the stream's WebRTC data channel, straight to the
  // emulator, no HTTP request and no gRPC hop through the gateway.
  const sendOverChannel = (coordinates, pressed) => {
    const touch = new Proto.Touch();
    touch.setX(coordinates.x);
    touch.setY(coordinates.y);
    touch.setIdentifier(0);
    touch.setPressure(pressed ? 1024 : 0);
    touch.setTouchMajor(pressed ? 8 : 0);
    touch.setTouchMinor(pressed ? 8 : 0);
    const event = new Proto.TouchEvent();
    event.setTouchesList([touch]);
    event.setDisplay(0);
    return sendInputEvent('touch', event);
  };

  const queueTouch = (coordinates, pressed, move = false) => {
    const sender = touchSender.current;
    // Use the channel only when no HTTP touch is pending, to keep the order.
    if (USE_DATA_CHANNEL && queueIdle(sender) && sendOverChannel(coordinates, pressed)) {
      if (inputPath.current === 'HTTP') pageLog('normal', tr('Les touches passent de nouveau par le canal de données'));
      inputPath.current = 'data channel';
      return;
    }
    // The session fell back to the server path: slower, worth a toast.
    if (inputPath.current !== 'HTTP') {
      pageLog('warning', tr('Les touches passent par le serveur (canal de données fermé) : elles peuvent être plus lentes'),
        { notify: true });
    }
    inputPath.current = 'HTTP';
    enqueue(sender, coordinates, pressed, move);
    pumpTouches();
  };

  // Local marker under the finger: immediate feedback while the video of
  // Android's reaction is still on its way.
  const showMarker = (event, visible) => {
    const marker = touchMarker.current;
    if (!marker) return;
    if (!markerShown) visible = false;
    const bounds = event.currentTarget.getBoundingClientRect();
    marker.style.transform = `translate(${event.clientX - bounds.left}px, ${event.clientY - bounds.top}px)`;
    marker.style.opacity = visible ? '1' : '0';
  };

  const startTouch = (event) => {
    event.preventDefault();
    pointerDown.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    showMarker(event, true);
    const coordinates = touchCoordinates(event);
    touchStart.current = { ...coordinates, time: performance.now() };
    queueTouch(coordinates, true);
  };

  const moveTouch = (event) => {
    if (!pointerDown.current) return;
    event.preventDefault();
    showMarker(event, true);
    queueTouch(touchCoordinates(event), true, true);
  };

  const endTouch = (event) => {
    if (!pointerDown.current) return;
    event.preventDefault();
    pointerDown.current = false;
    showMarker(event, false);
    const coordinates = touchCoordinates(event);
    queueTouch(coordinates, false);
    tellPlugins(coordinates, event.type === 'pointercancel');
  };

  // Plugins observe the user's touches (api.onTap), after they were sent.
  const tellPlugins = (end, cancelled) => {
    const start = touchStart.current;
    touchStart.current = null;
    if (!start || cancelled) return;
    emitTap(tapOf(start, end, performance.now(), display));
  };

  return {
    startTouch, moveTouch, endTouch, sendKey, touchMarker, pointerDown, inputPath, touchFailures,
  };
}
