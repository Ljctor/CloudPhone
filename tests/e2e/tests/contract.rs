//! Contract tests: what the emulator says through the gateway, checked the
//! same way on the fake and on a real instance, and printed so that a run
//! against the real one shows where the fake's guesses (marked UNVERIFIED in
//! tests/fake-emulator/fake_emulator.py) are wrong.
//!
//! By default they run on the fake. With the `smoke` feature they run on the
//! deployed instance at CLOUDPHONE_URL (one short extra viewer, no input):
//!
//!     CLOUDPHONE_URL=http://<server>:8000/ cargo test --features smoke --test contract -- --nocapture
use cloudphone_e2e::browser::{browser_test, Options};
use cloudphone_e2e::*;
use serde_json::{json, Value};
use std::time::Duration;

/// Opens a WebRTC session from the browser the way the page's driver does
/// (ws-jsep, an "input" data channel and recvonly video/audio of its own),
/// and gives what the emulator sent: JSEP messages, the offer's SDP, the
/// data channels it opened, and whether video arrived.
const SESSION_JS: &str = r#"
const url = arguments[0];
const out = window.__contract = {messages: [], channels: [], sdp: null, video: false, error: null, state: []};
const ws = new WebSocket(url);
let pc = null;
const start = (message) => {
  pc = new RTCPeerConnection({iceServers: (message.start && message.start.iceServers) || []});
  pc.ontrack = (e) => { if (e.track.kind === 'video') e.track.onunmute = () => { out.video = true; }; };
  pc.ondatachannel = (e) => {
    const c = e.channel;
    out.channels.push({label: c.label, id: c.id, ordered: c.ordered, maxRetransmits: c.maxRetransmits,
                       maxPacketLifeTime: c.maxPacketLifeTime, protocol: c.protocol, negotiated: c.negotiated});
  };
  pc.onicecandidate = (e) => { if (e.candidate) ws.send(JSON.stringify({candidate: e.candidate.candidate, sdpMid: e.candidate.sdpMid, sdpMLineIndex: e.candidate.sdpMLineIndex})); };
  pc.onconnectionstatechange = () => out.state.push(pc.connectionState);
};
ws.onmessage = async (event) => {
  let message;
  try { message = JSON.parse(event.data); } catch (e) { out.messages.push({raw: String(event.data).slice(0, 200)}); return; }
  // Shapes only: keys and types, the SDP kept apart.
  const shape = {};
  for (const [k, v] of Object.entries(message)) shape[k] = (v && typeof v === 'object') ? Object.keys(v) : typeof v;
  out.messages.push(shape);
  try {
    if (message.start) { start(message); return; }
    const sdp = message.sdp && typeof message.sdp === 'object' ? message.sdp : (message.type ? message : null);
    if (sdp && sdp.type === 'offer') {
      if (!pc) start({});
      out.sdp = sdp.sdp;
      await pc.setRemoteDescription(sdp);
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      ws.send(JSON.stringify({type: answer.type, sdp: answer.sdp}));
      return;
    }
    if (message.candidate !== undefined && pc) {
      const c = typeof message.candidate === 'string'
        ? {candidate: message.candidate, sdpMid: message.sdpMid ?? '0', sdpMLineIndex: message.sdpMLineIndex ?? 0}
        : message.candidate;
      await pc.addIceCandidate(c);
    }
  } catch (e) { out.error = String(e); }
};
ws.onerror = () => { out.error = 'websocket error'; };
window.__contractClose = () => { try { ws.send(JSON.stringify({bye: true})); } catch (e) {} ws.close(); if (pc) pc.close(); };
return true;
"#;

fn codecs(sdp: &str) -> Vec<String> {
    let mut found = Vec::new();
    let mut in_video = false;
    for line in sdp.lines() {
        if line.starts_with("m=") {
            in_video = line.starts_with("m=video");
        }
        if in_video {
            if let Some(rest) = line.strip_prefix("a=rtpmap:") {
                if let Some(name) = rest.split_whitespace().nth(1).and_then(|n| n.split('/').next()) {
                    if !found.iter().any(|f| f == name) {
                        found.push(name.to_string());
                    }
                }
            }
        }
    }
    found
}

#[test]
fn a_browser_session_gets_video_and_the_input_data_channels() {
    let cp = CloudPhone::contract_target();
    let url = cp.ws_url(&format!("api/v1/emulator/ws-jsep?viewer={}", viewer_id("contract")));
    browser_test(&cp, Options::without_video(), |page| async move {
        page.js(SESSION_JS, vec![json!(url)]).await;
        page
            .wait_js(
                "video and data channels on the contract session",
                Duration::from_secs(45),
                "const o = window.__contract; return o && (o.error || (o.video && o.channels.length >= 2)) ? o : null",
                vec![],
            )
            .await;
        page.sleep(Duration::from_secs(2)).await;
        let result = page.js("return window.__contract", vec![]).await;
        page.js("window.__contractClose && window.__contractClose()", vec![]).await;
        eprintln!("CONTRACT jsep messages (emulator → page, shapes): {}", result["messages"]);
        eprintln!("CONTRACT data channels: {}", result["channels"]);
        eprintln!("CONTRACT connection states: {}", result["state"]);
        let sdp = result["sdp"].as_str().unwrap_or_default();
        eprintln!("CONTRACT offer media lines: {:?}", sdp.lines().filter(|l| l.starts_with("m=")).collect::<Vec<_>>());
        eprintln!("CONTRACT offer video codecs: {:?}", codecs(sdp));
        eprintln!("CONTRACT offer has candidates inline: {}", sdp.contains("a=candidate"));
        assert!(result["error"].is_null(), "session error: {result}");
        assert!(result["video"] == true, "video arrived: {result}");
        let labels: Vec<&str> = result["channels"].as_array().unwrap().iter().filter_map(|c| c["label"].as_str()).collect();
        for needed in ["touch", "keyboard"] {
            assert!(labels.contains(&needed), "the emulator opens a {needed:?} data channel: {labels:?}");
        }
        assert!(sdp.contains("m=video"), "a video m-line");
        let video_codecs = codecs(sdp);
        assert!(video_codecs.iter().any(|c| ["VP8", "VP9", "H264", "AV1"].contains(&c.as_str())), "a codec Firefox decodes: {video_codecs:?}");
    });
}

#[test]
fn the_signalling_messages_have_the_shapes_the_driver_reads() {
    let cp = CloudPhone::contract_target();
    let viewer = Viewer::open(&cp, &viewer_id("contract-ws"));
    let offer = viewer.wait_message("an offer", Duration::from_secs(20), |m| {
        m["type"] == "offer" || m["sdp"]["type"] == "offer"
    });
    std::thread::sleep(Duration::from_secs(2));
    let messages = viewer.messages();
    viewer.close();
    let shapes: Vec<Value> = messages
        .iter()
        .map(|m| {
            let mut shape = serde_json::Map::new();
            for (k, v) in m.as_object().unwrap() {
                let kind = match v {
                    Value::Object(o) => json!(o.keys().collect::<Vec<_>>()),
                    Value::String(_) => json!("string"),
                    Value::Number(_) => json!("number"),
                    Value::Bool(_) => json!("bool"),
                    Value::Array(_) => json!("array"),
                    Value::Null => json!("null"),
                };
                shape.insert(k.clone(), kind);
            }
            Value::Object(shape)
        })
        .collect();
    eprintln!("CONTRACT signalling shapes: {}", json!(shapes));
    eprintln!("CONTRACT offer form: {}", if offer["type"] == "offer" { "flat {type, sdp}" } else { "nested {sdp: {type, sdp}}" });
    // What the driver handles: start, an offer (flat or nested), candidates
    // as a string or an object.
    for m in &messages {
        let known = m.get("start").is_some() || m.get("sdp").is_some() || m.get("type").is_some() || m.get("candidate").is_some() || m.get("bye").is_some();
        assert!(known, "a message the driver understands: {m}");
    }
}

#[test]
fn the_emulator_status_has_the_fields_the_page_reads() {
    let cp = CloudPhone::contract_target();
    let status = cp.get_json("api/v1/emulator/status");
    eprintln!("CONTRACT emulator status: {status}");
    let config = &status["platformConfig"];
    for key in ["hw.lcd.width", "hw.lcd.height"] {
        let value: u64 = config[key].as_str().and_then(|v| v.parse().ok()).unwrap_or_else(|| panic!("{key} as a number string: {status}"));
        assert!(value >= 320, "{key} = {value}");
    }
    let display = cp.get_json("api/v1/display");
    assert_eq!(config["hw.lcd.width"].as_str().unwrap(), display["running"]["width"].to_string(), "status and display agree: {display}");
    assert!(status["version"].as_str().is_some_and(|v| !v.is_empty()), "a version: {status}");
}

#[test]
fn the_state_has_the_fields_the_page_reads() {
    let cp = CloudPhone::contract_target();
    let state = cp.get_json("api/v1/state?details=1");
    eprintln!("CONTRACT state: {state}");
    for key in ["active", "sub"] {
        assert!(state["emulator"][key].is_string(), "emulator.{key}: {state}");
    }
    assert!(state["android"]["booted"].is_boolean() || state["android"]["booted"].is_null(), "{state}");
    assert!(state["viewers"].is_u64(), "{state}");
    assert!(state["load"]["one"].is_number() && state["load"]["cpus"].is_u64(), "{state}");
    let settings = cp.get_json("api/v1/emulator-settings");
    eprintln!("CONTRACT emulator settings: {settings}");
    assert!(settings["current"]["renderer"].is_string(), "{settings}");
}
