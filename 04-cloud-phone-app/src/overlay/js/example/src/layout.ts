// Where the Android screen and the toolbar go. No React, no DOM: the page
// passes the window's size and whether it is in fullscreen.
import { TOOLBAR_WIDTH } from './styles';

// Android's display size until the gateway reports the real one.
export const DEFAULT_DISPLAY = { width: 480, height: 1040 };

// Largest Android screen that fits, with the toolbar either beside it or
// below it, whichever leaves the bigger screen. A phone whose shape matches
// Android's (e.g. 19.5:9) gets the full width with the toolbar below.
// display: Android's size; viewport: the window's, in CSS pixels.
// Returns { width, height, toolbar: 'side' | 'below' | 'overlay' }.
export function fittedScreen(display, viewport, { fullscreen, folded, docked }) {
  const DEVICE_WIDTH = display.width;
  const DEVICE_HEIGHT = display.height;
  // Fullscreen or folded bar: the screen takes the whole window and the bar
  // floats over it, so a phone shaped like Android uses every pixel. A
  // docked bar keeps its own space, even in fullscreen.
  if ((fullscreen && !docked) || folded) {
    const width = Math.max(1, Math.floor(Math.min(viewport.width,
      viewport.height * DEVICE_WIDTH / DEVICE_HEIGHT)));
    return { width, height: Math.floor(width * DEVICE_HEIGHT / DEVICE_WIDTH), toolbar: 'overlay' };
  }
  const fit = (availableWidth, availableHeight) => {
    const width = Math.max(1, Math.floor(Math.min(availableWidth,
      availableHeight * DEVICE_WIDTH / DEVICE_HEIGHT)));
    return { width, height: Math.floor(width * DEVICE_HEIGHT / DEVICE_WIDTH) };
  };
  const side = fit(viewport.width - TOOLBAR_WIDTH, viewport.height);
  const below = fit(viewport.width, viewport.height - TOOLBAR_WIDTH);
  return below.width > side.width ? { ...below, toolbar: 'below' } : { ...side, toolbar: 'side' };
}

// The page's flex direction for the toolbar's place.
export function mainDirection(toolbar) {
  return toolbar === 'side' ? 'row' : 'column';
}

// Android's size from GET /api/v1/emulator/status, or null when it has
// none.
export function displayFromStatus(status) {
  const config = status?.platformConfig ?? {};
  const width = Number(config['hw.lcd.width']);
  const height = Number(config['hw.lcd.height']);
  return width > 0 && height > 0 ? { width, height } : null;
}

// The running screen size as a key (null until known): a new one means the
// gateway restarted on a new size.
export function sizeKey(running) {
  if (!running?.width) return null;
  return `${running.width}x${running.height}`;
}

// The toasts' top: below the banner while it shows.
export function toastsTop(bannerShown) {
  return bannerShown ? '72px' : '8px';
}
