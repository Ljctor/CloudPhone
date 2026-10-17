/**
 * @jest-environment node
 */
import { capVideoBitrate } from "../src/components/emulator/net/sdp_bitrate";

const ANSWER = [
  "v=0",
  "o=- 1 2 IN IP4 127.0.0.1",
  "s=-",
  "t=0 0",
  "m=video 9 UDP/TLS/RTP/SAVPF 96",
  "c=IN IP4 0.0.0.0",
  "a=rtcp:9 IN IP4 0.0.0.0",
  "a=mid:0",
  "m=application 9 UDP/DTLS/SCTP webrtc-datachannel",
  "c=IN IP4 0.0.0.0",
  "a=mid:1",
  "",
].join("\r\n");

describe("capVideoBitrate", () => {
  it("leaves the answer alone without a cap", () => {
    expect(capVideoBitrate(ANSWER, 0)).toBe(ANSWER);
    expect(capVideoBitrate(ANSWER, null)).toBe(ANSWER);
  });

  it("puts the cap after the c= line of the video section only", () => {
    const lines = capVideoBitrate(ANSWER, 300).split("\r\n");
    const c = lines.indexOf("c=IN IP4 0.0.0.0");
    expect(lines.slice(c + 1, c + 3)).toEqual(["b=AS:300", "b=TIAS:300000"]);
    expect(lines.filter((l) => l.startsWith("b="))).toHaveLength(2);
    expect(lines[lines.length - 1]).toBe("");
  });

  it("replaces an existing cap", () => {
    const capped = capVideoBitrate(capVideoBitrate(ANSWER, 1000), 300);
    expect(capped).toBe(capVideoBitrate(ANSWER, 300));
  });

  it("caps a video section that ends the answer, with \\n line ends", () => {
    const sdp = "v=0\nm=video 9 RTP/AVP 96\na=mid:0\n";
    expect(capVideoBitrate(sdp, 500)).toBe("v=0\nm=video 9 RTP/AVP 96\nb=AS:500\nb=TIAS:500000\na=mid:0\n");
    expect(capVideoBitrate("v=0\nm=video 9 RTP/AVP 96", 500)).toBe("v=0\nm=video 9 RTP/AVP 96\nb=AS:500\nb=TIAS:500000");
  });
});
