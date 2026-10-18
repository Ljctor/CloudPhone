//! The HTTP and WebSocket API as documented, seen from outside.
use cloudphone_e2e::*;
use serde_json::{json, Value};
use std::time::{Duration, Instant};

#[test]
fn ping_answers_204_at_once_with_no_body_and_no_caching() {
    let cp = CloudPhone::start();
    let start = Instant::now();
    let response = cp.get("api/v1/ping");
    let elapsed = start.elapsed();
    assert_eq!(response.status(), 204);
    assert_eq!(response.headers().get("cache-control").map(|v| v.to_str().unwrap().to_string()).as_deref(), Some("no-store"));
    assert!(response.bytes().is_empty(), "no body");
    assert!(elapsed < Duration::from_secs(1), "answered at once: {elapsed:?}");
}

#[test]
fn ping_answers_even_when_the_emulator_does_not() {
    let cp = CloudPhone::start();
    cp.fake().control(json!({"grpc": "down"}));
    assert_eq!(cp.get("api/v1/ping").status(), 204);
}

#[test]
fn api_answers_are_never_cached() {
    let cp = CloudPhone::start();
    for path in ["api/v1/state", "api/v1/display", "api/v1/emulator-settings", "api/v1/plugins", "api/v1/ping"] {
        let response = cp.get(path);
        assert!(response.status().is_success(), "GET {path}: {}", response.status());
        let cache = response.headers().get("cache-control").map(|v| v.to_str().unwrap().to_string());
        assert_eq!(cache.as_deref(), Some("no-store"), "GET {path}");
    }
}

/// DEVELOPMENT.md: "API answers `no-store`". The upstream emulator helper
/// routes answer without any Cache-Control (found by this test).
#[test]
fn upstream_emulator_status_is_not_cached_either() {
    let cp = CloudPhone::start();
    let response = cp.get("api/v1/emulator/status");
    assert!(response.status().is_success());
    let cache = response.headers().get("cache-control").map(|v| v.to_str().unwrap().to_string());
    assert_eq!(cache.as_deref(), Some("no-store"), "GET api/v1/emulator/status");
}

#[test]
fn json_endpoints_answer_json() {
    let cp = CloudPhone::start();
    for path in ["api/v1/state", "api/v1/display", "api/v1/emulator-settings", "api/v1/emulator/status", "api/v1/plugins"] {
        let response = cp.get(path);
        let kind = response.headers().get("content-type").map(|v| v.to_str().unwrap().to_string()).unwrap_or_default();
        assert!(kind.starts_with("application/json"), "GET {path}: {kind}");
        let _: Value = response.json().unwrap_or_else(|e| panic!("GET {path}: {e}"));
    }
}

#[test]
fn unknown_paths_are_404_and_post_only_routes_refuse_get() {
    let cp = CloudPhone::start();
    for path in ["api/v1/does-not-exist", "no-such-page.html", "assets/no-such-asset.js"] {
        assert_eq!(cp.get(path).status(), 404, "GET {path}");
    }
    for path in ["api/v1/emulator/key", "api/v1/emulator/touch", "api/v1/viewers/disconnect-others", "api/v1/emulator/gps"] {
        assert_eq!(cp.get(path).status(), 405, "GET {path}");
    }
}

#[test]
fn index_html_is_the_same_page_with_the_same_token() {
    let cp = CloudPhone::start();
    let root = cp.get("").text().unwrap();
    let response = cp.get("index.html");
    assert_eq!(response.status(), 200);
    assert_eq!(response.headers().get("cache-control").map(|v| v.to_str().unwrap().to_string()).as_deref(), Some("no-cache"));
    assert_eq!(response.text().unwrap(), root, "/ and /index.html serve the same page");
}

#[test]
fn the_token_is_stable_between_page_loads() {
    let cp = CloudPhone::start();
    let first = cp.page_token();
    let second = cp.page_token();
    assert_eq!(first, second, "one token per gateway start, not per page load");
    assert!(first.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_'), "token is URL-safe: {first}");
}

#[test]
fn every_viewer_id_starts_not_kicked() {
    let cp = CloudPhone::start();
    for id in ["", "e2e-unknown", "e2e-%20with%20spaces", "e2e-ünïcode"] {
        let state = cp.get_json(&format!("api/v1/state?viewer={id}"));
        assert_eq!(state["kicked"], false, "viewer {id:?}: {state}");
    }
}

#[test]
fn an_open_viewer_is_not_kicked() {
    let cp = CloudPhone::start();
    let viewer = Viewer::open(&cp, &viewer_id("kick"));
    std::thread::sleep(Duration::from_secs(1));
    let state = cp.get_json(&format!("api/v1/state?viewer={}", viewer.id));
    assert_eq!(state["kicked"], false, "{state}");
    assert!(!viewer.received().closed, "the server keeps the session open");
}

#[test]
fn viewers_grow_with_signalling_sessions_and_shrink_when_they_close() {
    let cp = CloudPhone::start();
    assert_eq!(cp.viewers(), 0);
    let sessions: Vec<Viewer> = (0..3).map(|i| Viewer::open(&cp, &viewer_id(&format!("count{i}")))).collect();
    cp.wait_viewers("three viewers", Duration::from_secs(10), |n| n == 3);
    for session in &sessions {
        assert!(!session.received().closed, "session {} stays open: {:?}", session.id, session.received());
    }
    let mut sessions = sessions.into_iter();
    sessions.next().unwrap().close();
    cp.wait_viewers("two viewers", Duration::from_secs(10), |n| n == 2);
    drop(sessions);
    cp.wait_viewers("no viewer", Duration::from_secs(10), |n| n == 0);
}

#[test]
fn the_signalling_socket_refuses_other_sites() {
    use tungstenite::client::IntoClientRequest;
    let cp = CloudPhone::start();
    let ws_url = cp.ws_url(&format!("api/v1/emulator/ws-jsep?viewer={}", viewer_id("origin")));
    let mut request = ws_url.as_str().into_client_request().unwrap();
    request.headers_mut().insert("Origin", "https://example.org".parse().unwrap());
    match tungstenite::connect(request) {
        Err(tungstenite::Error::Http(response)) => assert_eq!(response.status(), 403),
        Err(other) => panic!("expected HTTP 403, got {other}"),
        Ok(_) => panic!("a WebSocket from another site was accepted"),
    }
    assert_eq!(cp.viewers(), 0, "not counted as a viewer");
}

#[test]
fn posts_from_other_sites_are_refused_on_every_route() {
    let cp = CloudPhone::start();
    let token = cp.page_token();
    for path in ["api/v1/display", "api/v1/emulator-settings", "api/v1/viewers/disconnect-others", "api/v1/emulator/touch", "api/v1/emulator/key"] {
        let status = client()
            .post(cp.url(path))
            .header("X-CloudPhone-Token", &token)
            .header("Origin", "https://example.org")
            .json(&json!({}))
            .send()
            .unwrap()
            .status();
        assert_eq!(status, 403, "POST {path} from another site");
    }
}

#[test]
fn display_running_size_agrees_with_the_emulator_and_the_state() {
    let cp = CloudPhone::start();
    let display = cp.get_json("api/v1/display");
    let status = cp.get_json("api/v1/emulator/status");
    assert_eq!(status["booted"], true);
    let hw = &status["hardwareConfig"];
    assert_eq!(hw["hw.lcd.width"].as_str().unwrap().parse::<u64>().unwrap(), display["running"]["width"].as_u64().unwrap(), "{status} / {display}");
    assert_eq!(hw["hw.lcd.height"].as_str().unwrap().parse::<u64>().unwrap(), display["running"]["height"].as_u64().unwrap());
    assert_eq!(status["platformConfig"], status["hardwareConfig"], "both names, same values");
}

#[test]
fn the_emulators_own_screen_size_wins_when_it_reports_one() {
    // getStatus with hw.lcd.*: the gateway passes them on as they are.
    let cp = CloudPhone::start_with(json!({"options": {"status_lcd": true}}));
    let status = cp.get_json("api/v1/emulator/status");
    assert_eq!(status["platformConfig"]["hw.lcd.width"], "480", "{status}");
    assert_eq!(status["platformConfig"]["hw.lcd.density"], "213", "{status}");
}

#[test]
fn emulator_settings_agree_with_the_server_metrics() {
    let cp = CloudPhone::start();
    let settings = cp.get_json("api/v1/emulator-settings");
    let state = wait_for("server metrics", Duration::from_secs(15), || {
        let state = cp.get_json("api/v1/state?details=1");
        state["metrics"]["emulator"]["settings"]["renderer"].is_string().then_some(state)
    });
    let running = &state["metrics"]["emulator"]["settings"];
    assert_eq!(running, &settings["current"], "{running} / {settings}");
    let max_cores = settings["limits"]["maxCores"].as_u64().unwrap();
    assert!(max_cores <= state["load"]["cpus"].as_u64().unwrap(), "max cores {max_cores} within the host's threads");
}

#[test]
fn the_emulator_reports_its_version_and_vm() {
    let cp = CloudPhone::start();
    let status = cp.get_json("api/v1/emulator/status");
    assert!(status["version"].as_str().unwrap().starts_with("36."), "the pinned emulator 36.x: {status}");
    assert!(status["uptime"].as_u64().unwrap() > 0);
    assert_eq!(status["vmConfig"]["numberOfCpuCores"], 4, "{status}");
    assert_eq!(status["vmConfig"]["ramSizeBytes"], 4u64 << 30, "{status}");
}

#[test]
fn emulator_status_says_when_the_emulator_does_not_answer() {
    let cp = CloudPhone::start();
    cp.fake().control(json!({"grpc": "down"}));
    let response = cp.get("api/v1/emulator/status");
    assert_eq!(response.status(), 500);
    assert!(response.json().unwrap()["error"].is_string());
}

#[test]
fn logcat_and_gps_reach_the_emulator() {
    let cp = CloudPhone::start();
    let logcat = cp.get_json("api/v1/emulator/logcat?start=0");
    assert!(logcat["contents"].as_str().unwrap().contains("FakeAndroid"), "{logcat}");
    assert!(logcat["next"].as_u64().unwrap() > 0, "{logcat}");
    let response = cp.post_json("api/v1/emulator/gps", &json!({"latitude": 48.85, "longitude": 2.35}));
    assert_eq!(response.status(), 200, "{:?}", response.text());
    let calls = cp.fake().record()["grpc"].clone();
    assert!(calls.as_array().unwrap().iter().any(|c| c["method"] == "setPhysicalModel"), "{calls}");
}

#[test]
fn disconnect_others_closes_the_other_sessions_with_4001_and_flags_them_kicked() {
    let cp = CloudPhone::start();
    let me = Viewer::open(&cp, &viewer_id("keeper"));
    let other = Viewer::open(&cp, &viewer_id("kicked"));
    let third = Viewer::open(&cp, &viewer_id("kicked2"));
    cp.wait_viewers("three viewers", Duration::from_secs(10), |n| n == 3);
    let response = cp.post_json("api/v1/viewers/disconnect-others", &json!({"viewer": me.id}));
    assert_eq!(response.status(), 200, "{:?}", response.text());
    assert_eq!(response.json().unwrap(), json!({"closed": 2}));
    for v in [&other, &third] {
        wait_for("the other session to be closed", Duration::from_secs(10), || v.received().closed.then_some(()));
        assert_eq!(v.received().close_code, Some(4001), "{:?}", v.received());
        assert_eq!(cp.get_json(&format!("api/v1/state?viewer={}", v.id))["kicked"], true);
    }
    assert_eq!(cp.get_json(&format!("api/v1/state?viewer={}", me.id))["kicked"], false);
    assert!(!me.received().closed, "the caller keeps its session");
    cp.wait_viewers("only the caller", Duration::from_secs(10), |n| n == 1);
    // Refused for 10 minutes: the same id cannot come back, a new one can.
    let again = Viewer::open(&cp, &other.id);
    wait_for("the kicked id to be refused", Duration::from_secs(10), || again.received().closed.then_some(()));
    assert_eq!(again.received().close_code, Some(4001));
    let fresh = Viewer::open(&cp, &viewer_id("fresh"));
    fresh.wait_message("an offer for a new viewer id", Duration::from_secs(15), |m| m.to_string().contains("m=video"));
}

#[test]
fn disconnect_others_needs_a_viewer_id() {
    let cp = CloudPhone::start();
    for body in [json!({}), json!({"viewer": ""})] {
        assert_eq!(cp.post_json("api/v1/viewers/disconnect-others", &body).status(), 400, "{body}");
    }
}

#[test]
fn the_removed_emerald_route_is_gone() {
    // Moved to the Slayer Legend plugin (part 05).
    let cp = CloudPhone::start();
    assert_eq!(cp.get("api/v1/emerald-mask").status(), 404);
}
