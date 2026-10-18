//! The HTTP input fallback the page uses while no data channel is open:
//! keys through adb, touches through gRPC sendTouch. What arrives is read
//! from the fake emulator.
use cloudphone_e2e::*;
use serde_json::{json, Value};
use std::time::Duration;

#[test]
fn each_hardware_key_reaches_android_through_adb() {
    let cp = CloudPhone::start();
    let keys = [("GoBack", "BACK"), ("GoHome", "HOME"), ("AppSwitch", "APP_SWITCH"), ("Power", "POWER"), ("AudioVolumeUp", "VOLUME_UP"), ("AudioVolumeDown", "VOLUME_DOWN")];
    for (key, _) in keys {
        let response = cp.post_json("api/v1/emulator/key", &json!({"key": key}));
        assert_eq!(response.status(), 200, "{key}: {:?}", response.text());
    }
    let received: Vec<String> = cp.fake().keys().iter().map(|k| format!("{} {}", k["via"].as_str().unwrap(), k["key"].as_str().unwrap())).collect();
    let expected: Vec<String> = keys.iter().map(|(_, code)| format!("adb {code}")).collect();
    assert_eq!(received, expected, "in order, as Android key codes");
    let adb = cp.fake().record()["adb"].clone();
    assert!(adb.as_array().unwrap().iter().all(|c| c.as_str().unwrap().starts_with("-s emulator-5558 shell input keyevent")), "{adb}");
}

#[test]
fn unknown_keys_are_refused_before_adb() {
    let cp = CloudPhone::start();
    for body in [json!({"key": "Enter"}), json!({"key": "HOME"}), json!({}), json!({"key": "GoHome; reboot"})] {
        assert_eq!(cp.post_json("api/v1/emulator/key", &body).status(), 400, "{body}");
    }
    assert_eq!(cp.fake().record()["adb"], json!([]), "adb never ran");
}

#[test]
fn a_failing_adb_is_an_error_for_the_page() {
    let cp = CloudPhone::start_with(json!({"options": {"adb_fails": true}}));
    let response = cp.post_json("api/v1/emulator/key", &json!({"key": "GoHome"}));
    assert_eq!(response.status(), 500);
    assert!(response.json().unwrap()["error"].as_str().unwrap().contains("not found"), "adb's message is passed on");
}

#[test]
fn a_touch_reaches_android_with_its_coordinates_and_pressure() {
    let cp = CloudPhone::start();
    for (x, y, pressed) in [(100, 200, true), (110, 230, true), (110, 230, false)] {
        let response = cp.post_json("api/v1/emulator/touch", &json!({"x": x, "y": y, "pressed": pressed}));
        assert_eq!(response.status(), 200, "{:?}", response.text());
    }
    let touches = cp.fake().touches();
    let seen: Vec<(i64, i64, i64, i64, &str)> = touches
        .iter()
        .map(|t| (t["x"].as_i64().unwrap(), t["y"].as_i64().unwrap(), t["pressure"].as_i64().unwrap(), t["identifier"].as_i64().unwrap(), t["via"].as_str().unwrap()))
        .collect();
    assert_eq!(seen, [(100, 200, 1024, 0, "grpc"), (110, 230, 1024, 0, "grpc"), (110, 230, 0, 0, "grpc")]);
    assert_eq!(touches[0]["touch_major"], 8);
    assert_eq!(touches[2]["touch_major"], 0, "a release has no contact area");
}

#[test]
fn touches_outside_the_screen_are_clamped_to_its_edges() {
    let cp = CloudPhone::start();
    for (x, y) in [(-50, -50), (5000, 5000)] {
        assert_eq!(cp.post_json("api/v1/emulator/touch", &json!({"x": x, "y": y, "pressed": true})).status(), 200);
    }
    let seen: Vec<(i64, i64)> = cp.fake().touches().iter().map(|t| (t["x"].as_i64().unwrap(), t["y"].as_i64().unwrap())).collect();
    assert_eq!(seen, [(0, 0), (479, 1039)], "within the 480×1040 screen");
}

#[test]
fn a_touch_android_refuses_is_an_error_for_the_page() {
    let cp = CloudPhone::start_with(json!({"options": {"touch_fails": true}}));
    let response = cp.post_json("api/v1/emulator/touch", &json!({"x": 10, "y": 10, "pressed": true}));
    assert_eq!(response.status(), 500);
}

#[test]
fn touches_follow_the_screen_size_after_a_change() {
    let cp = CloudPhone::start();
    let token = cp.page_token();
    assert_eq!(cp.post_json("api/v1/display", &json!({"width": 360, "height": 780, "density": 160})).status(), 202);
    cp.wait_new_token(&token, Duration::from_secs(30));
    cp.wait_for_android(Duration::from_secs(20));
    assert_eq!(cp.post_json("api/v1/emulator/touch", &json!({"x": 5000, "y": 5000, "pressed": false})).status(), 200);
    let last = cp.fake().touches().last().cloned().unwrap();
    assert_eq!((last["x"].clone(), last["y"].clone()), (json!(359), json!(779)), "clamped to the new 360×780 screen");
}
