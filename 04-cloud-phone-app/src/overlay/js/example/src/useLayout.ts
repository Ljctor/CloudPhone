// The layout's inputs from the browser and the gateway: the window's size,
// Android's display size, the fitted screen kept up to date, and the reload
// after a size change. The sizes are worked out in layout.ts.
import { useEffect, useRef, useState } from 'react';
import { DEFAULT_DISPLAY, displayFromStatus, fittedScreen, sizeKey } from './layout';

export function viewportSize() {
  const viewport = window.visualViewport;
  return {
    width: Math.floor(viewport?.width || window.innerWidth),
    height: Math.floor(viewport?.height || window.innerHeight),
  };
}

function fitted(display, folded, docked) {
  return fittedScreen(display, viewportSize(), { fullscreen: Boolean(document.fullscreenElement), folded, docked });
}

// The gateway reads Android's display size from the running device, so
// layout and touch mapping follow the AVD instead of a constant.
export function useAndroidDisplay(gatewayUrl) {
  const [display, setDisplay] = useState(DEFAULT_DISPLAY);
  useEffect(() => {
    let cancelled = false;
    fetch(`${gatewayUrl}/api/v1/emulator/status`, { cache: 'no-store' })
      .then((response) => (response.ok ? response.json() : null))
      .then((status) => {
        const size = displayFromStatus(status);
        if (!cancelled && size) setDisplay(size);
      })
      .catch((error) => console.warn('Android display size:', error));
    return () => { cancelled = true; };
  }, [gatewayUrl]);
  return display;
}

// The screen fitted to the window, again on each resize or fullscreen change.
export function useFittedScreen(display, folded, docked) {
  const [screen, setScreen] = useState(() => fitted(DEFAULT_DISPLAY, false, false));
  useEffect(() => {
    const resize = () => setScreen(fitted(display, folded, docked));
    resize();
    window.addEventListener('resize', resize);
    window.visualViewport?.addEventListener('resize', resize);
    document.addEventListener('fullscreenchange', resize);
    return () => {
      window.removeEventListener('resize', resize);
      window.visualViewport?.removeEventListener('resize', resize);
      document.removeEventListener('fullscreenchange', resize);
    };
  }, [display, folded, docked]);
  return screen;
}

// A size change ends with the gateway restarting on the new size: reload
// so that layout, touch mapping and the stream all start fresh.
export function useReloadOnResize(displayState) {
  const firstSize = useRef(null);
  useEffect(() => {
    const size = sizeKey(displayState?.running);
    if (size === null) return;
    if (firstSize.current === null) firstSize.current = size;
    else if (size !== firstSize.current) window.location.reload();
  }, [displayState]);
}
