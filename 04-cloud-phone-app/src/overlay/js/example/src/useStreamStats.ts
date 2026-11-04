// Samples the stream once per STATS_INTERVAL_MS (the numbers are in
// streamStats.ts): ICE or HTTP ping, frames received and shown, the
// network details.
import { useEffect, useRef, useState } from 'react';
import { activePeerConnection } from '../../src/components/emulator/net/ws_jsep_protocol_driver';
import { streamDiagnostic } from '../../src/components/emulator/net/stream_diagnostics';
import { mediaStall, resetMediaWindow } from './streamHealth';
import { EMPTY_STATS, VIDEO_COUNTERS, emptySample, readReport, statsFrom } from './streamStats';

const STATS_INTERVAL_MS = 1000;

export function useStreamStats(deviceRef, gatewayUrl, { generation = 0, onMediaStall = null } = {}) {
  const stallCallback = useRef(onMediaStall);
  stallCallback.current = onMediaStall;
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
    let mediaHealth = null;
    let reportedStall = false;
    // Frames presented on screen, counted with requestVideoFrameCallback where
    // available: getVideoPlaybackQuality() stays at 0 for WebRTC streams in
    // some browsers.
    let presented = 0;
    let watchedVideo = null;
    let frameCallback = null;

    const watchFrames = (video) => {
      if (video === watchedVideo) return;
      if (watchedVideo && frameCallback !== null) watchedVideo.cancelVideoFrameCallback(frameCallback);
      watchedVideo = video;
      mediaHealth = null;
      reportedStall = false;
      presented = 0;
      frameCallback = null;
      if (!video || typeof video.requestVideoFrameCallback !== 'function') return;
      const onFrame = () => {
        if (stopped || watchedVideo !== video) return;
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
        if (watchedVideo && frameCallback !== null) {
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
          mediaHealth = null;
          reportedStall = false;
          previousConnection = connection;
        }
        if (connection) {
          try {
            readReport(await connection.getStats(), connection.connectionState, sampleData);
          } catch (error) {
            console.warn('Stream statistics:', error);
          }
        }
        if (stopped || connection !== activePeerConnection() || video !== deviceRef.current?.querySelector('video')) return;
        let pingSource = sampleData.ping === null ? null : 'ICE';
        if (sampleData.ping === null) {
          const start = performance.now();
          try {
            const response = await fetch(`${gatewayUrl}/api/v1/ping`, { cache: 'no-store', signal: AbortSignal.timeout(5000) });
            if (!response.ok) throw new Error('Ping refused');
            sampleData.ping = performance.now() - start;
            pingSource = 'HTTP';
          } catch {
            sampleData.ping = null;
          }
        }
        if (stopped || connection !== activePeerConnection() || video !== deviceRef.current?.querySelector('video')) return;
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
        const health = mediaStall(mediaHealth, {
          time: now, visible: !document.hidden,
          connected: connection?.connectionState === 'connected', paused: video?.paused ?? true,
          // Explicit framesReceived only: readReport's display fallback to
          // framesDecoded is not independent proof of arriving media frames.
          framesReceived: sampleData.details.framesReceived,
          framesDecoded: decoded, presented: shown,
          bytesReceived: sampleData.bytes, packetsReceived: sampleData.details.packetsReceived,
        });
        mediaHealth = health.state;
        if (health.evidence && !reportedStall) streamDiagnostic('media-stall-detected', health.evidence);
        reportedStall = Boolean(health.evidence);
        if (health.evidence) stallCallback.current?.({ connection, generation, evidence: health.evidence });
        if (connection && (sampledAt === 0 || now - sampledAt >= 5000)) {
          sampledAt = now;
          streamDiagnostic('stats', {
            ...Object.fromEntries(VIDEO_COUNTERS.map((key) => [key, sampleData.details[key] ?? null])),
            sampleTimeMs: now, jitterMs: sampleData.details.jitter ?? null,
            roundTripTimeMs: pingSource === 'ICE' ? sampleData.ping : null,
            connection: connection.connectionState, ice: connection.iceConnectionState,
            framesReceived: sampleData.received, framesDecoded: decoded ?? null,
            bytesReceived: sampleData.bytes, presented: shown,
            keyFramesDecoded: sampleData.details.keyFramesDecoded ?? null,
            packetsLost: sampleData.details.packetsLost ?? null,
            freezeCount: sampleData.details.freezeCount ?? null,
            totalFreezesDuration: sampleData.details.totalFreezesDuration ?? null,
            paused: video?.paused ?? true, readyState: video?.readyState ?? 0,
            width: video?.videoWidth ?? 0, height: video?.videoHeight ?? 0, hidden: document.hidden,
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

    const visibilityChanged = () => { mediaHealth = resetMediaWindow(mediaHealth); reportedStall = false; };
    document.addEventListener('visibilitychange', visibilityChanged);
    const timer = window.setInterval(sample, STATS_INTERVAL_MS);
    return () => {
      stopped = true;
      document.removeEventListener('visibilitychange', visibilityChanged);
      window.clearInterval(timer);
      if (watchedVideo && frameCallback !== null) watchedVideo.cancelVideoFrameCallback(frameCallback);
    };
  }, [deviceRef, gatewayUrl, generation]);

  return stats;
}
