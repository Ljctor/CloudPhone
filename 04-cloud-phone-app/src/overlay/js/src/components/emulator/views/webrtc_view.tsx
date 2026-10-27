/*
 * Copyright 2019 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
import React, { useEffect, useRef, useState } from "react";
import logger from "../net/logger";
import WsJsepProtocol from "../net/ws_jsep_protocol_driver";

export interface EmulatorWebrtcViewProps {
  /** The JSEP protocol driver instance. */
  jsep: WsJsepProtocol;
  /** Callback for connection state changes ("connecting", "connected", "disconnected"). */
  onStateChange?: (state: string) => void;
  /** Callback when audio track status changes. */
  onAudioStateChange?: (audio: boolean) => void;
  /** Whether the audio should be muted. */
  muted?: boolean;
  /** Audio volume (between 0.0 and 1.0). */
  volume?: number;
  /** Callback invoked on signaling or playback errors. */
  onError?: (error: Error) => void;
  /** Component width. */
  width?: number;
  /** Component height. */
  height?: number;
}

/**
 * A React component that renders the WebRTC video stream of the emulator.
 * Handles establishing the stream via the JSEP protocol driver and managing
 * local playback (including handling autoplay constraints).
 */
const EmulatorWebrtcView: React.FC<EmulatorWebrtcViewProps> = ({
  jsep,
  onStateChange,
  onAudioStateChange,
  muted = true,
  volume = 1.0,
  onError = (e) => logger.error("WebRTC error: " + e),
  width,
  height,
}) => {
  const startedAt = useRef<number>(performance.now());
  const [audio, setAudio] = useState<boolean>(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const hasRenderedFrame = useRef<boolean>(false);
  const [connect, setConnect] = useState<string>("connecting");

  useEffect(() => {
    if (onStateChange) {
      onStateChange(connect);
    }
  }, [connect, onStateChange]);

  useEffect(() => {
    if (onAudioStateChange) {
      onAudioStateChange(audio);
    }
  }, [audio, onAudioStateChange]);

  // The browser refused to start the video even muted (autoplay blocked
  // for all media): it waits for a gesture on the page.
  const blocked = useRef<boolean>(false);
  const frameCallback = useRef<number | null>(null);

  const onDisconnect = () => {
    hasRenderedFrame.current = false;
    blocked.current = false;
    setConnect("disconnected");
    setAudio(false);
  };

  // Start playing on the page's next gesture, once.
  const playOnGesture = () => {
    const events = ["pointerdown", "keydown", "touchend"];
    const onGesture = () => {
      events.forEach((name) => document.removeEventListener(name, onGesture, true));
      safePlay();
    };
    events.forEach((name) => document.addEventListener(name, onGesture, true));
  };

  const safePlay = async () => {
    const video = videoRef.current;
    if (!video) {
      // Component was unmounted.
      return;
    }
    try {
      await video.play();
      jsep.diagnostic("play-resolved", { paused: video.paused, muted: video.muted, readyState: video.readyState });
      logger.debug("Automatic playback started!");
    } catch (error: any) {
      jsep.diagnostic("play-rejected", { name: error?.name ?? "Error", muted: video.muted, readyState: video.readyState });
      if (error?.name !== "NotAllowedError" || !videoRef.current) {
        // AbortError: a new load interrupted this play(); canplay retries.
        onError(error);
        return;
      }
      // Audible autoplay refused: muted autoplay always is allowed, except
      // when the browser blocks all media.
      if (!video.muted) {
        video.muted = true;
        try {
          await video.play();
          return;
        } catch (again: any) {
          error = again;
        }
      }
      onError(error);
      blocked.current = true;
      setConnect("blocked");
      playOnGesture();
    }
  };

  // The first decoded frame, wherever it is seen first: a received WebRTC
  // track is not enough, the browser may have a live but muted track with
  // no decoded frame.
  const watchFrames = () => {
    const video = videoRef.current as any;
    if (!video || frameCallback.current !== null || typeof video.requestVideoFrameCallback !== "function") return;
    frameCallback.current = video.requestVideoFrameCallback(() => {
      frameCallback.current = null;
      onFirstFrame();
    });
  };

  const onConnect = (track: MediaStreamTrack) => {
    const video = videoRef.current;
    if (!video) {
      // Component was unmounted.
      return;
    }
    // Muted before the stream is attached: autoplay of a muted video is
    // allowed without a gesture.
    video.muted = muted;

    if (!video.srcObject) {
      video.srcObject = new MediaStream();
    }

    const stream = video.srcObject as MediaStream;
    if (!stream.getTracks().find((t) => t.id === track.id)) {
      stream.addTrack(track);
    }

    if (track.kind === "audio") {
      setAudio(true);
    } else {
      watchFrames();
      safePlay();
    }
  };

  const onCanPlay = () => {
    safePlay();
  };

  const onFirstFrame = () => {
    // loadeddata, playing or a presented frame prove that the video element
    // has an actual frame. Keep displaying that last frame when a static
    // Android screen temporarily reports `waiting`. A paused video (play
    // refused) is not connected: it waits for a gesture.
    const video = videoRef.current;
    if (!video || (blocked.current && video.paused)) return;
    if (!hasRenderedFrame.current) jsep.diagnostic("first-frame", {
      elapsedMs: Math.round(performance.now() - startedAt.current),
      width: video.videoWidth, height: video.videoHeight, readyState: video.readyState,
      paused: video.paused, muted: video.muted,
    });
    blocked.current = false;
    hasRenderedFrame.current = true;
    setConnect("connected");
  };

  const onWaiting = () => {
    jsep.diagnostic("video-waiting", { hadFrame: hasRenderedFrame.current });
    if (!hasRenderedFrame.current && !blocked.current) {
      setConnect("connecting");
    }
  };

  const onContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
  };

  useEffect(() => {
    startedAt.current = performance.now();
    jsep.startStream({
      onConnected: onConnect,
      onDisconnected: onDisconnect,
    });

    setConnect("connecting");
    const video = videoRef.current;
    const onVideoEvent = (event: Event) => jsep.diagnostic(`video-${event.type}`, {
      readyState: video?.readyState ?? 0, paused: video?.paused ?? true,
      muted: video?.muted ?? true, hidden: document.hidden,
    });
    const events = ["loadedmetadata", "stalled", "suspend", "pause", "volumechange", "error"];
    events.forEach((name) => video?.addEventListener(name, onVideoEvent));
    const firstFrameTimer = window.setTimeout(() => {
      if (!hasRenderedFrame.current) jsep.diagnostic("first-frame-timeout", {
        elapsedMs: Math.round(performance.now() - startedAt.current),
        readyState: video?.readyState ?? 0, paused: video?.paused ?? true,
        width: video?.videoWidth ?? 0, hidden: document.hidden,
      });
    }, 5000);

    return () => {
      window.clearTimeout(firstFrameTimer);
      events.forEach((name) => video?.removeEventListener(name, onVideoEvent));
      if (frameCallback.current !== null) (video as any)?.cancelVideoFrameCallback?.(frameCallback.current);
      jsep.disconnect();
    };
  }, []);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.volume = volume;
    }
  }, [volume]);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.muted = muted;
    }
  }, [muted]);

  return (
    <video
      ref={videoRef}
      style={{
        display: "block",
        position: "relative",
        width: width ? `${width}px` : "100%",
        height: height ? `${height}px` : "100%",
        objectFit: "contain",
        objectPosition: "center",
      }}
      muted={muted}
      autoPlay
      playsInline
      onContextMenu={onContextMenu}
      onCanPlay={onCanPlay}
      onLoadedData={onFirstFrame}
      onPlaying={onFirstFrame}
      onWaiting={onWaiting}
    />
  );
};

export default EmulatorWebrtcView;
