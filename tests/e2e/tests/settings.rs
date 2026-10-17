//! Android's renderer, cores and memory, set from the page.
use cloudphone_e2e::*;
use serde_json::json;
use std::time::Duration;

#[test]
fn settings_report_what_android_runs_with_and_the_choices() {
    let settings = get_json("api/v1/emulator-settings");
    assert_eq!(settings["canChange"], true, "{settings}");
    let renderers: Vec<&str> = settings["limits"]["renderers"].as_array().unwrap().iter().map(|v| v.as_str().unwrap()).collect();
    assert!(renderers.contains(&"lavapipe"), "{settings}");
    let current = &settings["current"];
    assert!(renderers.contains(&current["renderer"].as_str().unwrap()), "{settings}");
    assert!(settings["limits"]["maxMemoryMb"].as_u64().unwrap() >= 2048, "{settings}");
}

#[test]
fn invalid_settings_are_refused_without_restarting_android() {
    for body in [
        json!({"renderer": "host", "cores": 4, "memoryMb": 8192}),
        json!({"renderer": "lavapipe", "cores": 0, "memoryMb": 8192}),
        json!({"renderer": "lavapipe", "cores": 999, "memoryMb": 8192}),
        json!({"renderer": "lavapipe", "cores": 4, "memoryMb": 8000}),
        json!({"renderer": "lavapipe", "cores": 4, "memoryMb": 1024}),
        json!({"renderer": "lavapipe"}),
    ] {
        let response = post_json("api/v1/emulator-settings", &body);
        assert_eq!(response.status(), 400, "{body} -> {:?}", response.text());
    }
    assert_eq!(get_json("api/v1/emulator-settings")["request"]["state"], "idle");
}

/// Restarts Android twice (about 5 minutes): `cargo test -- --ignored`.
#[test]
#[ignore = "restarts Android"]
fn a_settings_change_restarts_android_with_the_new_settings() {
    let before = get_json("api/v1/emulator-settings")["current"].clone();
    let cores: u64 = before["cores"].as_str().unwrap().parse().unwrap();
    let other = if cores == 2 { 4 } else { 2 };
    let change = |cores: u64| {
        let body = json!({"renderer": before["renderer"], "cores": cores, "memoryMb": before["memoryMb"].as_str().unwrap().parse::<u64>().unwrap()});
        let response = wait_for("the change to be accepted", Duration::from_secs(150), || {
            let response = post_json("api/v1/emulator-settings", &body);
            (response.status() != 429).then_some(response)
        });
        assert_eq!(response.status(), 202, "{:?}", response.text());
        wait_for("Android with the new settings", Duration::from_secs(600), || {
            let settings = get_json("api/v1/emulator-settings");
            (settings["current"]["cores"] == json!(cores.to_string()) && settings["request"]["state"] == "done").then_some(())
        });
        wait_for_android(Duration::from_secs(600));
    };
    change(other);
    change(cores);
}
