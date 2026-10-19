//! The video stream's signalling, as the page's WebRTC client sees it, and
//! what the gateway relays to the emulator.
use cloudphone_e2e::*;
use serde_json::{json, Value};
use std::time::Duration;

#[test]
fn a_viewer_gets_start_then_an_offer_with_video_and_data_channels() {
    let cp = CloudPhone::start();
    let viewer = Viewer::open(&cp, &viewer_id("offer"));
    viewer.wait_message("an SDP offer", Duration::from_secs(15), |m| m.to_string().contains("m=video"));
    let messages = viewer.messages();
    assert!(messages[0]["start"].is_object(), "the first message starts the peer connection: {}", messages[0]);
    let offer = messages.iter().find(|m| m.to_string().contains("m=video")).unwrap();
    let sdp = offer["sdp"].as_str().or_else(|| offer["sdp"]["sdp"].as_str()).expect("the offer's SDP");
    assert!(sdp.contains("VP8"), "VP8 offered: {sdp}");
    assert!(!sdp.contains("H264"), "no H264: {sdp}");
    assert!(sdp.contains("m=application"), "data channels for input are offered too");
}

#[test]
fn ice_candidates_follow_the_offer() {
    let cp = CloudPhone::start();
    let viewer = Viewer::open(&cp, &viewer_id("candidates"));
    viewer.wait_message("an ICE candidate", Duration::from_secs(15), |m| !m["candidate"].is_null());
}

#[test]
fn each_viewer_gets_its_own_session_on_the_emulator() {
    let cp = CloudPhone::start();
    let a = Viewer::open(&cp, &viewer_id("a"));
    let b = Viewer::open(&cp, &viewer_id("b"));
    for v in [&a, &b] {
        v.wait_message("an offer", Duration::from_secs(15), |m| m.to_string().contains("m=video"));
    }
    let sessions = cp.fake().record()["sessions"].as_array().unwrap().len();
    assert_eq!(sessions, 2, "two RequestRtcStream calls");
}

#[test]
fn bye_from_the_page_reaches_the_emulator() {
    let cp = CloudPhone::start();
    let viewer = Viewer::open(&cp, &viewer_id("bye"));
    viewer.wait_message("an offer", Duration::from_secs(15), |m| m.to_string().contains("m=video"));
    viewer.close();
    cp.fake().wait_record("the bye relayed to the emulator", Duration::from_secs(10), |r| {
        r["jsep"]["from_browser"].as_array().unwrap().iter().any(|m| m["message"]["keys"] == json!(["bye"])).then_some(())
    });
    let record = cp.fake().record();
    assert!(!record["sessions"][0]["closed"].is_null(), "the session is closed on the emulator: {}", record["sessions"]);
}

#[test]
fn a_page_that_vanishes_without_bye_is_torn_down_on_the_emulator() {
    let cp = CloudPhone::start();
    let ws_url = cp.ws_url(&format!("api/v1/emulator/ws-jsep?viewer={}", viewer_id("vanish")));
    let (mut socket, _) = tungstenite::connect(ws_url.as_str()).expect("signalling WebSocket");
    let _ = socket.read();
    // The TCP connection goes away without a close frame or a bye.
    if let tungstenite::stream::MaybeTlsStream::Plain(stream) = socket.get_ref() {
        stream.shutdown(std::net::Shutdown::Both).unwrap();
    }
    drop(socket);
    cp.fake().wait_record("the gateway's own bye", Duration::from_secs(10), |r| {
        r["jsep"]["from_browser"].as_array().unwrap().iter().any(|m| m["message"]["keys"] == json!(["bye"])).then_some(())
    });
    cp.wait_viewers("the viewer to be gone", Duration::from_secs(10), |n| n == 0);
}

#[test]
fn the_gateway_relays_the_ice_servers_and_the_token() {
    let cp = CloudPhone::start();
    let viewer = Viewer::open(&cp, &viewer_id("ice"));
    let start = viewer.wait_message("start", Duration::from_secs(15), |m| m["start"].is_object());
    assert_eq!(start["start"]["ice_servers"], json!([{"urls": ["stun:stun.l.google.com:19302"]}]), "{start}");
    let calls = cp.fake().record()["grpc"].clone();
    let rtc: Vec<&Value> = calls.as_array().unwrap().iter().filter(|c| c["method"] == "RequestRtcStream").collect();
    assert!(!rtc.is_empty() && rtc.iter().all(|c| c["authorized"] == true), "with the discovery file's token: {calls}");
}

#[test]
fn a_session_on_a_stopped_emulator_is_closed_and_the_viewer_count_recovers() {
    let cp = CloudPhone::start();
    cp.fake().control(json!({"grpc": "down"}));
    let viewer = Viewer::open(&cp, &viewer_id("down"));
    wait_for("the socket to be closed", Duration::from_secs(10), || viewer.received().closed.then_some(()));
    cp.wait_viewers("no viewer left", Duration::from_secs(10), |n| n == 0);
}
