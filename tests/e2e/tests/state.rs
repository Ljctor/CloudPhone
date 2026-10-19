//! What the server tells the page about itself: GET /api/v1/state.
use cloudphone_e2e::*;
use serde_json::{json, Value};
use std::time::Duration;

/// Waits until the state (cached 2 s by the server) satisfies `accept`.
fn wait_state(cp: &CloudPhone, what: &str, accept: impl Fn(&Value) -> bool) -> Value {
    wait_for(what, Duration::from_secs(15), || {
        let state = cp.try_get_json("api/v1/state?viewer=e2e-state")?;
        accept(&state).then_some(state)
    })
}

#[test]
fn state_reports_the_emulator_android_and_viewers() {
    let cp = CloudPhone::start();
    let state = cp.get_json("api/v1/state?viewer=e2e-state");
    assert_eq!(state["emulator"], json!({"active": "active", "sub": "running", "result": "success", "restarts": 0}), "{state}");
    assert_eq!(state["android"]["booted"], true, "{state}");
    assert_eq!(state["viewers"], 0, "{state}");
    assert!(state["load"]["cpus"].as_u64().unwrap() >= 1, "{state}");
    assert_eq!(state["display"], json!({"state": "idle"}), "{state}");
    assert_eq!(state["kicked"], false, "a new viewer is not kicked");
}

#[test]
fn details_add_host_emulator_and_android_metrics() {
    let cp = CloudPhone::start();
    cp.get_json("api/v1/state?details=1");
    let state = wait_for("Android's metrics", Duration::from_secs(30), || {
        let state = cp.get_json("api/v1/state?details=1");
        state["metrics"]["android"]["fps"].is_number().then_some(state)
    });
    let metrics = &state["metrics"];
    assert!(metrics["host"]["cpu"].as_u64().unwrap() <= 100, "{metrics}");
    assert_eq!(metrics["host"]["memory"]["total"], 16384, "the host's memory (fake 16 GiB): {metrics}");
    assert_eq!(metrics["emulator"]["settings"], json!({"renderer": "lavapipe", "cores": "4", "memoryMb": "4096"}), "{metrics}");
    assert!(metrics["emulator"]["memory"].as_u64().unwrap() > 4096, "the unit's memory in MiB: {metrics}");
    let android = &metrics["android"];
    assert_eq!(android["app"], "com.example.fakegame", "the package of the top layer: {android}");
    assert_eq!(android["fps"], 30.0, "{android}");
    assert_eq!(android["memory"]["total"], 4096, "{android}");
    assert_eq!(android["memory"]["swapUsed"], 1024, "{android}");
}

#[test]
fn android_metrics_are_read_only_while_a_page_asks_for_them() {
    let cp = CloudPhone::start();
    std::thread::sleep(Duration::from_secs(6));
    let calls = |cp: &CloudPhone| cp.fake().record()["adb"].as_array().unwrap().iter().filter(|c| c.as_str().unwrap().contains("timestats")).count();
    assert_eq!(calls(&cp), 0, "no adb call while nobody looks at the server panel");
    cp.get_json("api/v1/state?details=1");
    cp.fake().wait_record("an adb call for Android's metrics", Duration::from_secs(15), |r| {
        r["adb"].as_array().unwrap().iter().any(|c| c.as_str().unwrap().contains("timestats")).then_some(())
    });
}

#[test]
fn a_failing_adb_leaves_android_metrics_empty_and_the_rest_working() {
    let cp = CloudPhone::start_with(json!({"options": {"adb_fails": true}}));
    cp.get_json("api/v1/state?details=1");
    std::thread::sleep(Duration::from_secs(6));
    let state = cp.get_json("api/v1/state?details=1");
    let android = &state["metrics"]["android"];
    assert!(android.is_null() || android["fps"].is_null(), "no Android figures: {state}");
    assert_eq!(state["android"]["booted"], true, "{state}");
}

#[test]
fn an_adb_that_cannot_start_empties_android_metrics_and_says_adb_is_offline() {
    let cp = CloudPhone::start();
    wait_for("Android's metrics", Duration::from_secs(30), || {
        cp.get_json("api/v1/state?details=1")["metrics"]["android"]["fps"].is_number().then_some(())
    });
    cp.fake().control(json!({"adb_missing": true}));
    let state = wait_for("Android's metrics gone", Duration::from_secs(30), || {
        let state = cp.get_json("api/v1/state?details=1");
        state["metrics"]["android"].is_null().then_some(state)
    });
    assert!(state["metrics"]["host"]["cpu"].is_number(), "the rest still there: {state}");
    let offline = wait_for("the adb offline record", Duration::from_secs(20), || {
        cp.get_json("api/v1/logs")["records"].as_array()?.iter()
            .find(|r| r["level"] == "error" && r["source"] == "adb" && r["text"].as_str().unwrap_or("").contains("adb ne joint plus Android"))
            .cloned()
    });
    assert_eq!(offline["notify"], true, "{offline}");
    // No stale figures come back while adb cannot start.
    std::thread::sleep(Duration::from_secs(6));
    assert!(cp.get_json("api/v1/state?details=1")["metrics"]["android"].is_null());
}

#[test]
fn the_emulator_units_states_are_reported_as_systemd_gives_them() {
    let cp = CloudPhone::start();
    for (active, sub, result) in [("failed", "failed", "exit-code"), ("activating", "auto-restart", "exit-code"), ("inactive", "dead", "success"), ("activating", "start", "success")] {
        cp.fake().control(json!({"unit": {"active": active, "sub": sub, "result": result, "restarts": 3}}));
        let state = wait_state(&cp, &format!("unit {active} ({sub})"), |s| s["emulator"]["active"] == active && s["emulator"]["sub"] == sub);
        assert_eq!(state["emulator"]["result"], result, "{state}");
        assert_eq!(state["emulator"]["restarts"], 3, "{state}");
    }
}

#[test]
fn android_booting_is_reported_as_not_booted() {
    let cp = CloudPhone::start_with(json!({"booted": false}));
    let state = cp.get_json("api/v1/state");
    assert_eq!(state["android"]["booted"], false, "{state}");
    cp.fake().control(json!({"booted": true}));
    wait_state(&cp, "booted", |s| s["android"]["booted"] == true);
}

#[test]
fn an_emulator_that_does_not_answer_is_reported_as_unknown() {
    let cp = CloudPhone::start();
    cp.fake().control(json!({"grpc": "down"}));
    let state = wait_state(&cp, "booted null", |s| s["android"]["booted"].is_null());
    assert_eq!(state["emulator"]["active"], "active", "the unit itself still runs: {state}");
}

#[test]
fn load_is_reported_from_the_host() {
    let cp = CloudPhone::start_with(json!({"load": 37.5}));
    let state = cp.get_json("api/v1/state");
    assert_eq!(state["load"]["one"], 37.5, "{state}");
    assert_eq!(state["load"]["five"], 37.5, "{state}");
    let cpus = state["load"]["cpus"].as_u64().unwrap();
    let cores = state["load"]["cores"].as_u64().unwrap();
    assert!(cores >= 1 && cores <= cpus, "cores {cores} ≤ threads {cpus}");
}

#[test]
fn state_is_shared_for_a_couple_of_seconds() {
    let cp = CloudPhone::start();
    let a = cp.get_json("api/v1/state?viewer=a");
    cp.fake().control(json!({"load": 9.0}));
    let b = cp.get_json("api/v1/state?viewer=b");
    assert_eq!(a["load"], b["load"], "cached: {a} / {b}");
    wait_state(&cp, "the new load after the cache", |s| s["load"]["one"] == 9.0);
}
