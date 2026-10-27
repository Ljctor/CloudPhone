// Samples the stream once per STATS_INTERVAL_MS (the numbers are in
// streamStats.ts): ICE or HTTP ping, frames received and shown, the
// network details.
import { useEffect, useState } from 'react';
import { activePeerConnection } from '../../src/components/emulator/net/ws_jsep_protocol_driver';
import { streamDiagnostic } from '../../src/components/emulator/net/stream_diagnostics';
import { EMPTY_STATS, emptySample, readReport, statsFrom } from './streamStats';

const STATS_INTERVAL_MS = 1000;

export function useStreamStats(deviceRef, gatewayUrl) {
  const [stats, setStats] = useState(EMPTY_STATS);

  useEffect(() => {
    let previous = null;
    let previousConnection = null;
    let sampledAt = 0;
    let frozen = false;
    let noPresentationSince = null;
    let decodedBefore = null;
    let busy = false;
    let stopped = false;
    // Frames presented on screen, counted with requestVideoFrameCallback where
    // available: getVideoPlaybackQuality() stays at 0 for WebRTC streams in
    // some browsers.
    let presented = 0;
    let watchedVideo = null;
    let frameCallback = null;

    const watchFrames = (video) => {
      if (!video || video === watchedVideo || typeof video.requestVideoFrameCallback !== 'function') return;
      if (watchedVideo && frameCallback !== null) watchedVideo.cancelVideoFrameCallback(frameCallback);
      watchedVideo = video;
      presented = 0;
      const onFrame = () => {
        presented += 1;
        if (!stopped && watchedVideo === video) frameCallback = video.requestVideoFrameCallback(onFrame);
      };
      frameCallback = video.requestVideoFrameCallback(onFrame);
    };

    const sample = async () => {
      if (busy) return;
      busy = true;
      try {
        const now = performance.now();
        const video = deviceRef.current?.querySelector('video');
        watchFrames(video);
        let shown = null;
        if (watchedVideo) {
          shown = presented;
        } else {
          const quality = video?.getVideoPlaybackQuality?.();
          shown = quality ? quality.totalVideoFrames - quality.droppedVideoFrames : null;
        }
        const sampleData = emptySample();
        const connection = activePeerConnection();
        if (connection !== previousConnection) {
          previous = null;
          decodedBefore = null;
          noPresentationSince = null;
          frozen = false;
          sampledAt = 0;
          previousConnection = connection;
        }
        if (connection) {
          try {
            readReport(await connection.getStats(), connection.connectionState, sampleData);
          } catch (error) {
            console.warn('Stream statistics:', error);
          }
        }
        if (stopped) return;
        let pingSource = sampleData.ping === null ? null : 'ICE';
        if (sampleData.ping === null) {
          const start = performance.now();
          try {
            await fetch(`${gatewayUrl}/api/v1/ping`, { cache: 'no-store' });
            sampleData.ping = performance.now() - start;
            pingSource = 'HTTP';
          } catch {
            sampleData.ping = null;
          }
        }
        if (stopped) return;
        // An unchanged Android screen can legitimately send no frames. Only
        // suspect presentation when decoding advances while presentation stops.
        const decoded = sampleData.details.framesDecoded;
        const presentationStopped = previous && shown !== null && previous.shown === shown;
        if (!document.hidden && presentationStopped && decoded !== null && decoded > decodedBefore) {
          noPresentationSince ??= now;
        } else {
          noPresentationSince = null;
        }
        const nextFrozen = noPresentationSince !== null && now - noPresentationSince >= 5000;
        if (nextFrozen !== frozen) {
          frozen = nextFrozen;
          streamDiagnostic(frozen ? 'presentation-stalled' : 'presentation-resumed', {
            framesDecoded: decoded ?? null, presented: shown, hidden: document.hidden,
          });
        }
        decodedBefore = decoded;
        if (connection && now - sampledAt >= 10000) {
          sampledAt = now;
          streamDiagnostic('stats', {
            connection: connection.connectionState, ice: connection.iceConnectionState,
            framesReceived: sampleData.received, framesDecoded: decoded ?? null,
            bytesReceived: sampleData.bytes, presented: shown,
            keyFramesDecoded: sampleData.details.keyFramesDecoded ?? null,
            packetsLost: sampleData.details.packetsLost ?? null,
            freezeCount: sampleData.details.freezeCount ?? null,
            totalFreezesDuration: sampleData.details.totalFreezesDuration ?? null,
            paused: video?.paused ?? true, readyState: video?.readyState ?? 0,
            width: video?.videoWidth ?? 0, hidden: document.hidden,
          });
        }
        const current = { time: now, received: sampleData.received, shown, bytes: sampleData.bytes };
        if (!stopped) {
          setStats(statsFrom(previous, current, {
            ...sampleData.details,
            ping: sampleData.ping,
            pingSource,
            video: video?.videoWidth ? { width: video.videoWidth, height: video.videoHeight } : null,
          }));
        }
        previous = current;
      } finally {
        busy = false;
      }
    };

    const timer = window.setInterval(sample, STATS_INTERVAL_MS);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      if (watchedVideo && frameCallback !== null) watchedVideo.cancelVideoFrameCallback(frameCallback);
    };
  }, [deviceRef, gatewayUrl]);

  return stats;
}
