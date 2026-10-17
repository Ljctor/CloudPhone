// Caps the bitrate the emulator sends to this page. The emulator encodes one
// stream per viewer and honours the bandwidth lines of the answer it gets:
// "b=AS:<kbit/s>" and "b=TIAS:<bit/s>" in the video section. Its encoder then
// lowers the image size or the frame rate to fit.

/**
 * Returns `sdp` with every video section capped at `kbps` kbit/s, replacing
 * any bandwidth line already there. No cap (0, null or undefined) removes
 * nothing and returns `sdp` unchanged.
 */
export function capVideoBitrate(sdp: string, kbps?: number | null): string {
  if (!kbps || kbps <= 0) return sdp;
  const eol = sdp.includes("\r\n") ? "\r\n" : "\n";
  const lines = sdp.split(eol);
  const out: string[] = [];
  const cap = [`b=AS:${Math.round(kbps)}`, `b=TIAS:${Math.round(kbps * 1000)}`];
  let video = false;
  let pending = false; // video section whose cap is not written yet
  for (const line of lines) {
    if (line.startsWith("m=")) {
      if (pending) out.push(...cap);
      video = line.startsWith("m=video");
      pending = video;
      out.push(line);
      continue;
    }
    if (video && (line.startsWith("b=AS:") || line.startsWith("b=TIAS:"))) continue;
    // RFC 8866 order: m=, i=, c=, b=, then the rest.
    if (pending && !line.startsWith("i=") && !line.startsWith("c=")) {
      out.push(...cap);
      pending = false;
    }
    out.push(line);
  }
  if (pending) {
    // Video section at the end: keep the final empty line last.
    const last = out.length && out[out.length - 1] === "" ? out.pop() : undefined;
    out.push(...cap);
    if (last !== undefined) out.push(last);
  }
  return out.join(eol);
}
