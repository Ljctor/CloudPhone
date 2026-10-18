//! The gateway around a restarting emulator: it follows a new emulator
//! process (new discovery file, new token) by exiting, and systemd (the
//! fake, here) starts it again; it stays up while Android is down so the
//! page can say what is happening.
use cloudphone_e2e::*;
use serde_json::{json, Value};
use std::time::Duration;

fn gateway_runs(cp: &CloudPhone) -> Vec<Value> {
    cp.fake().record()["gateway"].as_array().cloned().unwrap()
}

#[test]
fn the_gateway_follows_a_new_emulator_process() {
    let cp = CloudPhone::start();
    let token = cp.page_token();
    cp.fake().action("replace_discovery");
    // It notices within its 5 s check, exits with 75 (restart me), and
    // comes back on the new discovery file.
    cp.wait_new_token(&token, Duration::from_secs(20));
    let runs = gateway_runs(&cp);
    assert_eq!(runs.len(), 2, "{runs:?}");
    assert_eq!(runs[0]["exit"], 75, "the first gateway exits with 75: {runs:?}");
    assert_ne!(runs[0]["discovery"], runs[1]["discovery"]);
    cp.wait_for_android(Duration::from_secs(10));
    let calls = cp.fake().record()["grpc"].clone();
    let last = calls.as_array().unwrap().last().unwrap().clone();
    assert_eq!(last["authorized"], true, "the new gateway uses the new token: {last}");
}

#[test]
fn until_it_restarts_the_gateway_reports_android_as_unreachable() {
    let cp = CloudPhone::start_with(json!({"options": {"gateway_restart_seconds": 3}}));
    cp.fake().action("replace_discovery");
    // The old token is refused by the new emulator: booted unknown.
    wait_for("booted null with the old token", Duration::from_secs(10), || {
        let state = cp.try_get_json("api/v1/state")?;
        state["android"]["booted"].is_null().then_some(())
    });
    let calls = cp.fake().record()["grpc"].clone();
    assert!(calls.as_array().unwrap().iter().any(|c| c["authorized"] == false), "a call with the old token: {calls}");
}

#[test]
fn a_crash_is_reported_then_android_comes_back_by_itself() {
    let cp = CloudPhone::start_with(json!({"options": {"crash_seconds": 4, "boot_seconds": 12}}));
    cp.fake().action("crash");
    let state = wait_for("the unit in auto-restart", Duration::from_secs(10), || {
        let s = cp.try_get_json("api/v1/state")?;
        (s["emulator"]["sub"] == "auto-restart").then_some(s)
    });
    assert_eq!(state["emulator"]["active"], "activating", "{state}");
    assert_eq!(state["emulator"]["restarts"], 1, "{state}");
    assert!(state["android"]["booted"].is_null(), "no emulator to ask: {state}");
    wait_for("Android booting", Duration::from_secs(20), || {
        let s = cp.try_get_json("api/v1/state")?;
        (s["emulator"]["active"] == "active" && s["android"]["booted"] == false).then_some(())
    });
    cp.wait_for_android(Duration::from_secs(40));
    assert_eq!(gateway_runs(&cp).len(), 2, "the gateway restarted once to follow the new emulator");
}

#[test]
fn the_gateway_waits_for_an_emulator_before_starting() {
    // files/libexec/cloudphone-gateway waits for a discovery file: started
    // while Android is down, the gateway comes up once Android is back.
    let cp = CloudPhone::start_with(json!({"options": {"crash_seconds": 4}}));
    cp.fake().action("stop_gateway");
    cp.fake().action("crash");
    cp.fake().action("start_gateway");
    std::thread::sleep(Duration::from_secs(2));
    assert!(client().get(cp.url("api/v1/ping")).send().is_err(), "no gateway while there is no emulator");
    wait_for("the gateway once Android is back", Duration::from_secs(20), || cp.try_get_json("api/v1/state"));
}

#[test]
fn an_open_viewer_is_disconnected_when_the_gateway_restarts() {
    let cp = CloudPhone::start();
    let viewer = Viewer::open(&cp, &viewer_id("restart"));
    viewer.wait_message("an offer", Duration::from_secs(15), |m| m.to_string().contains("m=video"));
    cp.fake().action("replace_discovery");
    wait_for("the socket to close", Duration::from_secs(20), || viewer.received().closed.then_some(()));
}
