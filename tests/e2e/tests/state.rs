//! What the page shows about the server.
use cloudphone_e2e::*;

#[test]
fn state_reports_the_emulator_android_and_viewers() {
    let state = get_json("api/v1/state?viewer=e2e-state");
    assert!(state["emulator"]["active"].is_string(), "{state}");
    assert!(state["android"]["booted"].is_boolean() || state["android"]["booted"].is_null(), "{state}");
    assert!(state["viewers"].is_u64(), "{state}");
    assert!(state["load"]["cpus"].as_u64().unwrap() >= 1, "{state}");
    assert_eq!(state["kicked"], false, "a new viewer is not kicked");
}

#[test]
fn details_add_host_emulator_and_android_metrics() {
    get_json("api/v1/state?details=1");
    let state = wait_for("server metrics", std::time::Duration::from_secs(30), || {
        let state = get_json("api/v1/state?details=1");
        state["metrics"]["emulator"]["settings"]["renderer"].is_string().then_some(state)
    });
    let metrics = &state["metrics"];
    let cpu = metrics["host"]["cpu"].as_u64().expect("host CPU percent");
    assert!(cpu <= 100, "{metrics}");
    assert!(metrics["host"]["memory"]["total"].as_u64().unwrap() > 0, "{metrics}");
    assert!(metrics["emulator"]["settings"]["cores"].is_string(), "{metrics}");
}
