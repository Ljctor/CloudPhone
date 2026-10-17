//! The video stream's signalling, as the page's WebRTC client sees it.
use cloudphone_e2e::*;
use std::time::{Duration, Instant};
use tungstenite::Message;

#[test]
fn the_signalling_socket_offers_a_video_stream() {
    let ws_url = url(&format!("api/v1/emulator/ws-jsep?viewer=e2e-{}", std::process::id())).replacen("http", "ws", 1);
    let (mut socket, _) = tungstenite::connect(ws_url.as_str()).expect("signalling WebSocket");
    if let tungstenite::stream::MaybeTlsStream::Plain(stream) = socket.get_ref() {
        stream.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
    }
    let start = Instant::now();
    let mut offer = None;
    while start.elapsed() < Duration::from_secs(30) && offer.is_none() {
        match socket.read() {
            Ok(Message::Text(text)) if text.contains("m=video") => offer = Some(text.to_string()),
            Ok(_) => {}
            Err(tungstenite::Error::Io(e)) if e.kind() == std::io::ErrorKind::WouldBlock || e.kind() == std::io::ErrorKind::TimedOut => {}
            Err(e) => panic!("signalling socket: {e}"),
        }
    }
    let offer = offer.expect("an SDP offer with a video track within 30 s");
    assert!(offer.contains("VP8") || offer.contains("VP9") || offer.contains("H264"), "a known video codec: {offer}");
    let _ = socket.send(Message::Text("{\"bye\":true}".into()));
    let _ = socket.close(None);
}
