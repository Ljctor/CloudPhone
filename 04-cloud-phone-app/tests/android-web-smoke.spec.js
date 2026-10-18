const { test, expect } = require('@playwright/test');
// The page to test: CLOUDPHONE_URL, e.g. http://127.0.0.1:18100/ through an
// SSH tunnel, or the gateway on this machine.
const PAGE_URL = process.env.CLOUDPHONE_URL || 'http://127.0.0.1:8000/';

test.use({
  viewport: { width: 360, height: 780 },
  launchOptions: {
    args: ['--autoplay-policy=no-user-gesture-required'],
  },
});

test('stream loads and refresh creates exactly one replacement session', async ({ page }) => {
  const browserErrors = [];
  const signalingSockets = [];
  page.on('console', (message) => {
    if (message.type() === 'error') browserErrors.push(message.text());
  });
  page.on('pageerror', (error) => browserErrors.push(error.message));
  page.on('websocket', (socket) => {
    if (socket.url().includes('/api/v1/emulator/ws-jsep')) {
      signalingSockets.push(socket.url());
    }
  });

  await page.addInitScript(() => {
    const NativePeerConnection = window.RTCPeerConnection;
    window.__peerConnections = [];
    window.RTCPeerConnection = function (...args) {
      const peer = new NativePeerConnection(...args);
      window.__peerConnections.push(peer);
      return peer;
    };
    window.RTCPeerConnection.prototype = NativePeerConnection.prototype;
  });

  await page.goto(`${PAGE_URL}?e2e=${Date.now()}`, {
    waitUntil: 'domcontentloaded',
  });

  const spinner = page.getByText('Connexion au flux…');
  const status = page.locator('[aria-label^="Connexion "]');
  const refresh = page.getByRole('button', { name: 'Reconnecter la vidéo' });
  const video = page.locator('video');

  await expect(video).toHaveCount(1);
  await page.waitForTimeout(12000);
  const diagnostics = await page.evaluate(async () => {
    const videoElement = document.querySelector('video');
    const peers = await Promise.all((window.__peerConnections || []).map(async (peer) => {
      const inbound = [];
      for (const report of (await peer.getStats()).values()) {
        if (report.type === 'inbound-rtp') {
          inbound.push({
            kind: report.kind,
            bytesReceived: report.bytesReceived,
            packetsReceived: report.packetsReceived,
            framesReceived: report.framesReceived,
            framesDecoded: report.framesDecoded,
          });
        }
      }
      return {
        connectionState: peer.connectionState,
        iceConnectionState: peer.iceConnectionState,
        iceGatheringState: peer.iceGatheringState,
        signalingState: peer.signalingState,
        inbound,
      };
    }));
    return {
      video: videoElement && {
        readyState: videoElement.readyState,
        networkState: videoElement.networkState,
        paused: videoElement.paused,
        currentTime: videoElement.currentTime,
        videoWidth: videoElement.videoWidth,
        videoHeight: videoElement.videoHeight,
        tracks: videoElement.srcObject
          ? videoElement.srcObject.getTracks().map((track) => ({
              kind: track.kind,
              readyState: track.readyState,
              muted: track.muted,
              enabled: track.enabled,
            }))
          : [],
      },
      peers,
    };
  });
  console.log('WEBRTC_DIAGNOSTICS=' + JSON.stringify({ diagnostics, browserErrors }));
  await expect(status).toHaveAttribute('aria-label', 'Connexion connected', {
    timeout: 20000,
  });
  await expect(spinner).toBeHidden();

  const firstVideoState = await video.evaluate((element) => ({
    readyState: element.readyState,
    paused: element.paused,
    currentTime: element.currentTime,
    width: element.videoWidth,
    height: element.videoHeight,
  }));
  expect(firstVideoState.readyState).toBeGreaterThanOrEqual(2);
  expect(firstVideoState.paused).toBe(false);
  expect(firstVideoState.width).toBeGreaterThan(0);
  expect(firstVideoState.height).toBeGreaterThan(0);

  await refresh.click();
  await refresh.click();
  await expect(spinner).toBeVisible();
  await expect(status).toHaveAttribute('aria-label', 'Connexion connecting');
  await expect(status).toHaveAttribute('aria-label', 'Connexion connected', {
    timeout: 20000,
  });
  await expect(spinner).toBeHidden();

  await page.waitForTimeout(1500);
  const replacementVideoState = await video.evaluate((element) => ({
    readyState: element.readyState,
    paused: element.paused,
    currentTime: element.currentTime,
    width: element.videoWidth,
    height: element.videoHeight,
  }));
  expect(replacementVideoState.readyState).toBeGreaterThanOrEqual(2);
  expect(replacementVideoState.paused).toBe(false);
  expect(replacementVideoState.currentTime).toBeGreaterThanOrEqual(0);
  expect(replacementVideoState.width).toBeGreaterThan(0);
  expect(replacementVideoState.height).toBeGreaterThan(0);

  expect(signalingSockets).toHaveLength(2);
  expect(browserErrors).toEqual([]);
});

test('a notify record from the server shows as a closable toast', async ({ browser }) => {
  // French page, whatever the browser's language.
  const context = await browser.newContext({ locale: 'fr-FR' });
  const first = await context.newPage();
  await first.goto(`${PAGE_URL}?e2e=${Date.now()}`, { waitUntil: 'domcontentloaded' });
  await expect(first.locator('[aria-label^="Connexion "]')).toHaveCount(1);
  // The page's first read of the log fills the lists; toasts are for what
  // comes after it.
  await first.waitForTimeout(6000);

  // Another device connects: the gateway logs it with notify.
  const second = await context.newPage();
  await second.goto(`${PAGE_URL}?e2e=${Date.now()}`, { waitUntil: 'domcontentloaded' });
  const toast = first.locator('[data-toast]', { hasText: 'Un autre appareil s’est connecté' });
  await expect(toast).toBeVisible({ timeout: 20000 });
  await expect(toast).toHaveAttribute('data-toast', 'normal');
  await expect(toast.locator('span').first()).toHaveCSS('color', 'rgb(255, 255, 255)');
  await toast.getByRole('button', { name: 'Fermer la notification' }).click();
  await expect(toast).toHaveCount(0);

  await second.close();
  await context.close();
});
