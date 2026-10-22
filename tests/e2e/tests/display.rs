//! Android's screen size, set from the page: POST /api/v1/display.
//! Every change here restarts the fake's Android, never a real one.
use cloudphone_e2e::*;
use serde_json::{json, Value};
use std::time::Duration;

fn wait_display(cp: &CloudPhone, what: &str, timeout: Duration, accept: impl Fn(&Value) -> bool) -> Value {
    wait_for(what, timeout, || {
        let display = cp.try_get_json("api/v1/display")?;
        accept(&display).then_some(display)
    })
}

#[test]
fn display_reports_the_configured_size_and_the_limits() {
    let cp = CloudPhone::start();
    let display = cp.get_json("api/v1/display");
    assert_eq!(display["running"], json!({"width": 480, "height": 1040}), "{display}");
    assert_eq!(display["configured"], json!({"width": 480, "height": 1040, "density": 213}), "{display}");
    assert_eq!(display["request"], json!({"state": "idle"}), "{display}");
    assert_eq!(display["canChange"], true);
    assert_eq!(display["limits"], json!({"width": [240, 1440], "height": [320, 3200], "density": [80, 640]}));
}

#[test]
fn invalid_sizes_are_refused_and_nothing_is_requested() {
    let cp = CloudPhone::start();
    for body in [
        json!({"width": 361, "height": 780, "density": 160}),
        json!({"width": 100, "height": 780, "density": 160}),
        json!({"width": 360, "height": 9000, "density": 160}),
        json!({"width": 360, "height": 780, "density": 79}),
        json!({"width": 360, "height": 780, "density": 641}),
        json!({"width": 238, "height": 780, "density": 160}),
        json!({"width": 1442, "height": 780, "density": 160}),
        json!({"width": 360, "height": 318, "density": 160}),
        json!({"width": 360, "height": 781, "density": 160}),
        json!({"width": 360}),
        json!({}),
        // Sizes given as strings, floats or booleans.
        json!({"width": "360", "height": 780, "density": 160}),
        json!({"width": 360, "height": "780", "density": 160}),
        json!({"width": 360, "height": 780, "density": "160"}),
        json!({"width": 360.0, "height": 780, "density": 160}),
        json!({"width": true, "height": 780, "density": 160}),
        json!({"width": null, "height": 780, "density": 160}),
        json!([360, 780, 160]),
    ] {
        let response = cp.post_json("api/v1/display", &body);
        assert_eq!(response.status(), 400, "{body} -> {:?}", response.text());
    }
    let response = client().post(cp.url("api/v1/display")).header("X-CloudPhone-Token", cp.page_token()).body("not json").send().unwrap();
    assert_eq!(response.status(), 400, "a body that is not JSON");
    std::thread::sleep(Duration::from_millis(500));
    assert_eq!(cp.fake().record()["requests"]["display"], json!([]), "nothing reached the root service");
    assert_eq!(cp.get_json("api/v1/display")["request"]["state"], "idle");
}

#[test]
fn a_size_change_restarts_android_at_the_new_size() {
    let cp = CloudPhone::start();
    let token = cp.page_token();
    let response = cp.post_json("api/v1/display", &json!({"width": 360, "height": 780, "density": 160}));
    assert_eq!(response.status(), 202, "{:?}", response.text());
    assert_eq!(response.json().unwrap(), json!({"status": "pending"}));
    // The gateway restarts on the new size (set-resolution.sh restarts it).
    cp.wait_new_token(&token, Duration::from_secs(30));
    let display = wait_display(&cp, "the change to be done", Duration::from_secs(30), |d| d["request"]["state"] == "done");
    assert_eq!(display["request"], json!({"state": "done", "width": 360, "height": 780, "density": 160}));
    assert_eq!(display["running"], json!({"width": 360, "height": 780}), "{display}");
    assert_eq!(display["configured"], json!({"width": 360, "height": 780, "density": 160}), "{display}");
    let status = cp.get_json("api/v1/emulator/status");
    assert_eq!(status["platformConfig"]["hw.lcd.width"], "360", "{status}");
    assert_eq!(status["platformConfig"]["hw.lcd.height"], "780", "{status}");
    let record = cp.fake().record();
    let requests: Vec<&Value> = record["requests"]["display"].as_array().unwrap().iter().collect();
    assert_eq!(requests[0]["request"], "360 780 160", "the line written for the root service: {requests:?}");
    let statuses: Vec<&str> = requests.iter().filter_map(|r| r["status"].as_str()).collect();
    assert_eq!(statuses, ["applying 360 780 160", "done 360 780 160"]);
    let android: Vec<&str> = record["events"].as_array().unwrap().iter().map(|e| e["event"].as_str().unwrap()).filter(|e| e.starts_with("android-")).collect();
    assert_eq!(android, ["android-stop", "android-start", "android-booted"], "Android restarted once");
    cp.wait_for_android(Duration::from_secs(10));
}

#[test]
fn the_state_says_a_size_change_is_on_its_way() {
    let cp = CloudPhone::start_with(json!({"options": {"hold_requests": true}}));
    assert_eq!(cp.post_json("api/v1/display", &json!({"width": 720, "height": 1560, "density": 320})).status(), 202);
    let state = wait_for("the state to say pending", Duration::from_secs(10), || {
        let s = cp.try_get_json("api/v1/state")?;
        (s["display"]["state"] == "pending").then_some(s)
    });
    assert_eq!(state["display"], json!({"state": "pending"}));
    cp.fake().control(json!({"hold_requests": false, "apply_seconds": 3}));
    let state = wait_for("the state to say applying", Duration::from_secs(10), || {
        let s = cp.try_get_json("api/v1/state")?;
        (s["display"]["state"] == "applying").then_some(s)
    });
    assert_eq!(state["display"], json!({"state": "applying", "width": 720, "height": 1560, "density": 320}));
}

#[test]
fn a_second_change_while_one_is_pending_is_refused_with_409() {
    let cp = CloudPhone::start_with(json!({"options": {"hold_requests": true}}));
    assert_eq!(cp.post_json("api/v1/display", &json!({"width": 360, "height": 780, "density": 160})).status(), 202);
    let second = cp.post_json("api/v1/display", &json!({"width": 720, "height": 1560, "density": 320}));
    assert_eq!(second.status(), 409, "{:?}", second.text());
    // Android settings are a change too: refused while a size is pending.
    let settings = cp.post_json("api/v1/emulator-settings", &json!({"renderer": "lavapipe", "cores": 1, "memoryMb": 4096}));
    assert_eq!(settings.status(), 409, "{:?}", settings.text());
    assert_eq!(cp.get_json("api/v1/display")["request"]["state"], "pending");
}

#[test]
fn a_failed_change_is_reported_and_android_keeps_running() {
    let cp = CloudPhone::start_with(json!({"options": {"fail_next": {"display": "set-resolution.sh: journalctl -u cloudphone-display"}}}));
    assert_eq!(cp.post_json("api/v1/display", &json!({"width": 360, "height": 780, "density": 160})).status(), 202);
    let display = wait_display(&cp, "the failure", Duration::from_secs(15), |d| d["request"]["state"] == "failed");
    assert_eq!(display["request"]["message"], "set-resolution.sh: journalctl -u cloudphone-display", "{display}");
    assert_eq!(display["running"], json!({"width": 480, "height": 1040}), "the size did not change");
    assert_eq!(cp.get_json("api/v1/state")["display"]["state"], "failed");
    assert!(cp.fake().record()["events"].as_array().unwrap().is_empty(), "Android was not restarted");
}

#[test]
fn a_second_change_within_two_minutes_is_refused_with_429() {
    let cp = CloudPhone::start_with(json!({"options": {"fail_next": {"display": "boom"}}}));
    assert_eq!(cp.post_json("api/v1/display", &json!({"width": 360, "height": 780, "density": 160})).status(), 202);
    wait_display(&cp, "the failure", Duration::from_secs(15), |d| d["request"]["state"] == "failed");
    let again = cp.post_json("api/v1/display", &json!({"width": 360, "height": 780, "density": 160}));
    assert_eq!(again.status(), 429, "{:?}", again.text());
    let error = again.json().unwrap()["error"].as_str().unwrap().to_string();
    assert!(error.starts_with("Wait ") && error.ends_with(" s before the next change"), "{error}");
    // The same limit covers Android settings.
    let settings = cp.post_json("api/v1/emulator-settings", &json!({"renderer": "lavapipe", "cores": 1, "memoryMb": 4096}));
    assert_eq!(settings.status(), 429, "{:?}", settings.text());
    let refused = settings.json().unwrap();
    assert_eq!(refused["error_t"]["template"], "Attendez {seconds} s avant le prochain changement", "{refused}");
}

/// docs/DEVELOPMENT.md: "one change per 2 minutes (429 otherwise)". A
/// successful change restarts the gateway, which forgets when the last
/// change was made.
#[test]
fn the_two_minute_limit_holds_after_a_successful_change() {
    let cp = CloudPhone::start();
    let token = cp.page_token();
    assert_eq!(cp.post_json("api/v1/display", &json!({"width": 360, "height": 780, "density": 160})).status(), 202);
    cp.wait_new_token(&token, Duration::from_secs(30));
    wait_display(&cp, "the change to be done", Duration::from_secs(30), |d| d["request"]["state"] == "done");
    let again = cp.post_json("api/v1/display", &json!({"width": 480, "height": 1040, "density": 213}));
    assert_eq!(again.status(), 429, "a second size change a few seconds after the first: {:?}", again.text());
}
