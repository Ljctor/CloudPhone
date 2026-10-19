// Touches on the page as Android sees them: the mapping from the page's
// pointer to Android's pixels, the order HTTP touches go in, and what
// plugins are told about a touch. No React, no DOM.

// Android's pixel under the pointer at (clientX, clientY) over a surface
// at bounds ({ left, top, width, height }) showing a display of
// display.width × display.height, clamped to the display.
export function touchPoint(clientX, clientY, bounds, display) {
  return {
    x: Math.max(0, Math.min(display.width - 1,
      Math.round((clientX - bounds.left) * display.width / bounds.width))),
    y: Math.max(0, Math.min(display.height - 1,
      Math.round((clientY - bounds.top) * display.height / bounds.height))),
  };
}

// Touch updates sent to the gateway: at most one request in flight. Press
// and release are queued in order; while a request runs, intermediate moves
// collapse into the latest one, so a drag never lags behind the finger.
export function touchQueue() {
  return { inFlight: false, queue: [], pendingMove: null };
}

// Nothing waiting or running: the data channel can take the next touch
// without passing an HTTP one.
export function queueIdle(sender) {
  return !sender.inFlight && sender.queue.length === 0 && !sender.pendingMove;
}

// Adds a touch to the queue; move: a move while pressed, which replaces the
// previous move not sent yet.
export function enqueue(sender, coordinates, pressed, move) {
  if (move) {
    sender.pendingMove = { ...coordinates, pressed: true };
  } else {
    if (sender.pendingMove) {
      sender.queue.push(sender.pendingMove);
      sender.pendingMove = null;
    }
    sender.queue.push({ ...coordinates, pressed });
  }
}

// The next touch to send, taken off the queue; none while one is in flight.
export function takeNext(sender) {
  if (sender.inFlight) return undefined;
  let next = sender.queue.shift();
  if (!next && sender.pendingMove) {
    next = sender.pendingMove;
    sender.pendingMove = null;
  }
  return next;
}

// What plugins are told (api.onTap) about a touch from start ({ x, y,
// time }) to end ({ x, y }) at now (ms): tap, long press (500 ms,
// Android's long-press time) or swipe (moved more than 4 % of the screen's
// width), as fractions of the screen.
export function tapOf(start, end, now, display) {
  const moved = Math.hypot(end.x - start.x, end.y - start.y) > display.width * 0.04;
  const kind = moved ? 'swipe' : now - start.time >= 500 ? 'long' : 'tap';
  const tap = { x: start.x / display.width, y: start.y / display.height, kind };
  if (moved) tap.end = { x: end.x / display.width, y: end.y / display.height };
  return tap;
}
