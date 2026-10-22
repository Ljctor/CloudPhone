//! Android's renderer, cores and memory, and optionally its screen, set
//! from the page in one request: POST /api/v1/emulator-settings. Every
//! change here restarts the fake's Android, never a real one.
use cloudphone_e2e::*;
use serde_json::{json, Value};
use std::time::Duration;

fn wait_settings(cp: &CloudPhone, what: &str, accept: impl Fn(&Value) -> bool) -> Value {
    wait_for(what, Duration::from_secs(30), || {
        let settings = cp.try_get_json("api/v1/emulator-settings")?;
        accept(&settings).then_some(settings)
    })
}

/// A valid change on any machine: cores within the host's threads.
fn change(cp: &CloudPhone) -> Value {
    let limits = cp.get_json("api/v1/emulator-settings")["limits"].clone();
    json!({"renderer": "swiftshader", "cores": limits["maxCores"].as_u64().unwrap().min(2), "memoryMb": 6144})
}

fn android_events(cp: &CloudPhone) -> Vec<String> {
    cp.fake().record()["events"].as_array().unwrap().iter().map(|e| e["event"].as_str().unwrap().to_string()).filter(|e| e.starts_with("android-")).collect()
}

#[test]
fn settings_report_what_android_runs_with_and_the_choices() {
    let cp = CloudPhone::start();
    let settings = cp.get_json("api/v1/emulator-settings");
    assert_eq!(settings["canChange"], true, "{settings}");
    assert_eq!(settings["current"], json!({"renderer": "lavapipe", "cores": "4", "memoryMb": "4096"}), "from the emulator's command line: {settings}");
    assert_eq!(settings["display"], json!({"width": 480, "height": 1040, "density": 213}), "{settings}");
    assert_eq!(settings["limits"]["renderers"], json!(["lavapipe", "swiftshader", "swangle", "software"]));
    assert_eq!(settings["limits"]["maxMemoryMb"], 14336, "16 GiB host minus 2 GiB, in 512 MiB steps: {settings}");
    let state = cp.get_json("api/v1/state");
    assert_eq!(settings["limits"]["maxCores"], state["load"]["cpus"], "at most every host thread");
    assert_eq!(settings["request"], json!({"state": "idle"}));
}

#[test]
fn invalid_settings_are_refused_and_nothing_is_requested() {
    let cp = CloudPhone::start();
    let max = cp.get_json("api/v1/emulator-settings")["limits"]["maxCores"].as_u64().unwrap();
    for body in [
        json!({"renderer": "host", "cores": 1, "memoryMb": 4096}),
        json!({"renderer": "lavapipe", "cores": 0, "memoryMb": 4096}),
        json!({"renderer": "lavapipe", "cores": max + 1, "memoryMb": 4096}),
        json!({"renderer": "lavapipe", "cores": 1, "memoryMb": 4000}),
        json!({"renderer": "lavapipe", "cores": 1, "memoryMb": 1024}),
        json!({"renderer": "lavapipe", "cores": 1, "memoryMb": 14848}),
        json!({"renderer": "lavapipe"}),
        json!({"renderer": 1, "cores": 1, "memoryMb": 4096}),
        // Numbers given as strings, floats or booleans.
        json!({"renderer": "lavapipe", "cores": "1", "memoryMb": 4096}),
        json!({"renderer": "lavapipe", "cores": 1, "memoryMb": "4096"}),
        json!({"renderer": "lavapipe", "cores": 1.0, "memoryMb": 4096}),
        json!({"renderer": "lavapipe", "cores": true, "memoryMb": 4096}),
        // The screen: all three values or none, integers, in bounds, even.
        json!({"renderer": "lavapipe", "cores": 1, "memoryMb": 4096, "width": 360}),
        json!({"renderer": "lavapipe", "cores": 1, "memoryMb": 4096, "width": 360, "height": 780}),
        json!({"renderer": "lavapipe", "cores": 1, "memoryMb": 4096, "width": "360", "height": 780, "density": 160}),
        json!({"renderer": "lavapipe", "cores": 1, "memoryMb": 4096, "width": 360, "height": "780", "density": 160}),
        json!({"renderer": "lavapipe", "cores": 1, "memoryMb": 4096, "width": 360, "height": 780, "density": "160"}),
        json!({"renderer": "lavapipe", "cores": 1, "memoryMb": 4096, "width": 361, "height": 780, "density": 160}),
        json!({"renderer": "lavapipe", "cores": 1, "memoryMb": 4096, "width": 360, "height": 780, "density": 700}),
        json!({"renderer": "lavapipe", "cores": 1, "memoryMb": 4096, "width": 200, "height": 780, "density": 160}),
    ] {
        let response = cp.post_json("api/v1/emulator-settings", &body);
        assert_eq!(response.status(), 400, "{body} -> {:?}", response.text());
    }
    std::thread::sleep(Duration::from_millis(500));
    assert_eq!(cp.fake().record()["requests"]["settings"], json!([]), "nothing reached the root service");
    assert_eq!(cp.get_json("api/v1/emulator-settings")["request"]["state"], "idle");
}

#[test]
fn a_settings_change_restarts_android_once_with_the_new_settings() {
    let cp = CloudPhone::start();
    let token = cp.page_token();
    let body = change(&cp);
    let response = cp.post_json("api/v1/emulator-settings", &body);
    assert_eq!(response.status(), 202, "{:?}", response.text());
    let cores = body["cores"].as_u64().unwrap();
    let settings = wait_settings(&cp, "the change to be done", |s| s["request"]["state"] == "done");
    assert_eq!(settings["request"], json!({"state": "done", "renderer": "swiftshader", "cores": cores.to_string(), "memoryMb": "6144"}));
    // The gateway follows the new emulator by itself (new discovery file).
    cp.wait_new_token(&token, Duration::from_secs(30));
    let settings = cp.get_json("api/v1/emulator-settings");
    assert_eq!(settings["current"], json!({"renderer": "swiftshader", "cores": cores.to_string(), "memoryMb": "6144"}), "{settings}");
    assert_eq!(settings["display"], json!({"width": 480, "height": 1040, "density": 213}), "the screen did not change");
    let requests = &cp.fake().record()["requests"]["settings"];
    assert_eq!(requests[0]["request"], format!("swiftshader {cores} 6144"), "{requests}");
    assert_eq!(android_events(&cp), ["android-stop", "android-start", "android-booted"], "one restart");
    cp.wait_for_android(Duration::from_secs(10));
}

#[test]
fn settings_and_a_screen_size_in_one_request_restart_android_once() {
    let cp = CloudPhone::start();
    let mut body = change(&cp);
    body["width"] = json!(720);
    body["height"] = json!(1560);
    body["density"] = json!(320);
    assert_eq!(cp.post_json("api/v1/emulator-settings", &body).status(), 202);
    let cores = body["cores"].as_u64().unwrap();
    let settings = wait_settings(&cp, "the change to be done", |s| s["request"]["state"] == "done");
    assert_eq!(
        settings["request"],
        json!({"state": "done", "renderer": "swiftshader", "cores": cores.to_string(), "memoryMb": "6144", "width": "720", "height": "1560", "density": "320"})
    );
    let display = wait_for("the gateway on the new size", Duration::from_secs(30), || {
        let d = cp.try_get_json("api/v1/display")?;
        (d["running"] == json!({"width": 720, "height": 1560})).then_some(d)
    });
    assert_eq!(display["configured"], json!({"width": 720, "height": 1560, "density": 320}));
    assert_eq!(android_events(&cp), ["android-stop", "android-start", "android-booted"], "one restart for both");
    assert_eq!(cp.fake().record()["requests"]["display"], json!([]), "no separate screen size request");
}

#[test]
fn the_page_sees_the_change_applying() {
    let cp = CloudPhone::start_with(json!({"options": {"apply_seconds": 3}}));
    let body = change(&cp);
    assert_eq!(cp.post_json("api/v1/emulator-settings", &body).status(), 202);
    let settings = wait_settings(&cp, "applying", |s| s["request"]["state"] == "applying");
    assert_eq!(settings["request"]["renderer"], "swiftshader", "{settings}");
}

#[test]
fn a_second_change_while_one_is_pending_is_refused_with_409() {
    let cp = CloudPhone::start_with(json!({"options": {"hold_requests": true}}));
    let body = change(&cp);
    assert_eq!(cp.post_json("api/v1/emulator-settings", &body).status(), 202);
    assert_eq!(cp.get_json("api/v1/emulator-settings")["request"], json!({"state": "pending"}));
    let again = cp.post_json("api/v1/emulator-settings", &body);
    assert_eq!(again.status(), 409, "{:?}", again.text());
    assert_eq!(again.json().unwrap()["error_t"], json!({"template": "Un changement est déjà en cours", "params": {}}),
               "a status text the page shows");
    let templates = cp.get_json("api/v1/templates");
    assert_eq!(templates["Un changement est déjà en cours"], "A change is already in progress", "{templates}");
    let size = cp.post_json("api/v1/display", &json!({"width": 360, "height": 780, "density": 160}));
    assert_eq!(size.status(), 409, "a screen size change is refused too: {:?}", size.text());
}

#[test]
fn a_failed_change_is_reported_with_its_reason() {
    let cp = CloudPhone::start_with(json!({"options": {"fail_next": {"settings": "restart: journalctl -u cloudphone-emulator"}}}));
    assert_eq!(cp.post_json("api/v1/emulator-settings", &change(&cp)).status(), 202);
    let settings = wait_settings(&cp, "the failure", |s| s["request"]["state"] == "failed");
    assert_eq!(settings["request"]["message"], "restart: journalctl -u cloudphone-emulator");
    assert_eq!(settings["current"]["renderer"], "lavapipe", "unchanged");
    assert!(android_events(&cp).is_empty(), "Android was not restarted");
    let again = cp.post_json("api/v1/emulator-settings", &change(&cp));
    assert_eq!(again.status(), 429, "one change per 2 minutes, failed or not: {:?}", again.text());
}

#[test]
fn the_root_service_refuses_what_the_gateway_lets_through() {
    // The root service checks again (hostile request file): the gateway's
    // limits and the service's agree, so nothing valid is refused there.
    let cp = CloudPhone::start();
    let max = cp.get_json("api/v1/emulator-settings")["limits"]["maxMemoryMb"].as_u64().unwrap();
    let body = json!({"renderer": "swangle", "cores": 1, "memoryMb": max});
    assert_eq!(cp.post_json("api/v1/emulator-settings", &body).status(), 202);
    let settings = wait_settings(&cp, "the change to be done", |s| ["done", "failed"].contains(&s["request"]["state"].as_str().unwrap_or("")));
    assert_eq!(settings["request"]["state"], "done", "the largest memory offered is accepted by the root service: {settings}");
}
