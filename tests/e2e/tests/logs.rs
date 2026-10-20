//! The gateway's log (GET /api/v1/logs): one stream of records {time,
//! level, source, text, notify?}, levels normal, warning and error, a
//! cursor to read only new ones. Failures forced on the fake emulator
//! (emulator gone, adb offline or never answering, a bad or failing
//! screen size request) must give records of the right level, errors
//! saying what to do next; events the page shows as toasts carry notify.
use cloudphone_e2e::*;
use serde_json::{json, Value};
use std::time::Duration;

const SOON: Duration = Duration::from_secs(20);

fn records(cp: &CloudPhone) -> Vec<Value> {
    cp.get_json("api/v1/logs")["records"].as_array().cloned().unwrap()
}

/// Waits for a record of `level` from `source` whose text contains `text`.
fn wait_record(cp: &CloudPhone, level: &str, source: &str, text: &str, timeout: Duration) -> Value {
    wait_for(&format!("a {level} record from {source} saying {text:?}"), timeout, || {
        let all = cp.try_get_json("api/v1/logs")?;
        all["records"].as_array()?.iter()
            .find(|r| r["level"] == level && r["source"] == source && r["text"].as_str().unwrap_or("").contains(text))
            .cloned()
    })
}

#[test]
fn records_have_one_shape_and_a_cursor_gives_only_new_ones() {
    let cp = CloudPhone::start();
    let first = cp.get("api/v1/logs");
    assert_eq!(first.status(), 200);
    assert_eq!(first.headers()["cache-control"], "no-store");
    let body = first.json().unwrap();
    let cursor = body["cursor"].as_str().expect("a cursor").to_string();
    let all = body["records"].as_array().unwrap().clone();
    let start = all.iter().find(|r| r["text"] == "Le gateway a démarré").expect("the gateway's start");
    assert_eq!((start["level"].as_str(), start["source"].as_str(), &start["notify"]), (Some("normal"), Some("gateway"), &json!(true)));
    for record in &all {
        assert!(record["time"].as_f64().is_some(), "{record}");
        assert!(["normal", "warning", "error"].contains(&record["level"].as_str().unwrap()), "only three levels: {record}");
        assert!(["gateway", "emulator", "adb"].contains(&record["source"].as_str().unwrap()), "{record}");
        assert!(record["text"].is_string(), "{record}");
        assert!(record["notify"].is_null() || record["notify"] == true, "{record}");
    }
    // Nothing new since the cursor; one record after a refused request.
    let again = cp.get_json(&format!("api/v1/logs?since={cursor}"));
    assert_eq!(again["records"], json!([]), "{again}");
    assert_eq!(cp.post_json("api/v1/display", &json!({"width": 361, "height": 780, "density": 160})).status(), 400);
    let after = cp.get_json(&format!("api/v1/logs?since={cursor}"));
    let new: Vec<&Value> = after["records"].as_array().unwrap().iter().collect();
    assert_eq!(new.len(), 1, "{after}");
    assert_ne!(after["cursor"], cursor);
    // A garbled cursor gets everything kept.
    assert!(cp.get_json("api/v1/logs?since=nonsense")["records"].as_array().unwrap().len() > new.len());
}

#[test]
fn the_log_is_refused_to_other_sites() {
    let cp = CloudPhone::start();
    let response = client().get(cp.url("api/v1/logs")).header("Origin", "http://example.com").send().unwrap();
    assert_eq!(response.status(), 403);
}

#[test]
fn an_emulator_crash_is_an_error_record_saying_what_to_do_with_notify() {
    let cp = CloudPhone::start_with(json!({"options": {"crash_seconds": 30}}));
    cp.fake().action("crash");
    let record = wait_record(&cp, "error", "emulator", "Android a planté", SOON);
    assert_eq!(record["notify"], true, "{record}");
    assert!(record["text"].as_str().unwrap().contains("relancez-le sur le serveur"), "says what to do: {record}");
    assert_eq!(record["template"].as_str().map(|t| t.contains("{result}")), Some(true), "translatable: {record}");
}

#[test]
fn an_emulator_that_stops_on_an_error_is_an_error_record() {
    let cp = CloudPhone::start();
    cp.fake().control(json!({"unit": {"active": "failed", "sub": "failed", "result": "exit-code"}}));
    let record = wait_record(&cp, "error", "emulator", "Android s’est arrêté sur une erreur (exit-code)", SOON);
    assert!(record["text"].as_str().unwrap().contains("il faut le relancer sur le serveur"), "{record}");
    assert_eq!(record["notify"], true);
}

#[test]
fn adb_offline_is_an_error_record_and_its_return_a_normal_one() {
    let cp = CloudPhone::start_with(json!({"options": {"adb_fails": true}}));
    assert_eq!(cp.post_json("api/v1/emulator/key", &json!({"key": "GoHome"})).status(), 500);
    let record = wait_record(&cp, "error", "adb", "adb ne joint plus Android", SOON);
    assert_eq!(record["notify"], true, "{record}");
    assert!(record["text"].as_str().unwrap().contains("not found"), "adb's reason: {record}");
    assert!(record["text"].as_str().unwrap().contains("relancez-le sur le serveur"), "{record}");
    // Said once while it lasts.
    assert_eq!(cp.post_json("api/v1/emulator/key", &json!({"key": "GoHome"})).status(), 500);
    let offline = records(&cp).iter().filter(|r| r["source"] == "adb" && r["level"] == "error").count();
    assert_eq!(offline, 1);
    cp.fake().control(json!({"adb_fails": false}));
    assert_eq!(cp.post_json("api/v1/emulator/key", &json!({"key": "GoHome"})).status(), 200);
    wait_record(&cp, "normal", "adb", "adb joint de nouveau Android", SOON);
}

#[test]
fn a_key_adb_never_answers_is_an_error_within_its_timeout() {
    let cp = CloudPhone::start_with(json!({"options": {"adb_hangs": true}}));
    let asked = std::time::Instant::now();
    assert_eq!(cp.post_json("api/v1/emulator/key", &json!({"key": "GoHome"})).status(), 500);
    assert!(asked.elapsed() < Duration::from_secs(15), "answered after the 10 s timeout: {:?}", asked.elapsed());
    let record = wait_record(&cp, "error", "gateway", "Error sending key: adb did not answer within 10 s", SOON);
    assert!(record["text"].as_str().unwrap().contains("Check Android in Information"), "says what to do: {record}");
    cp.fake().control(json!({"adb_hangs": false}));
    assert_eq!(cp.post_json("api/v1/emulator/key", &json!({"key": "GoHome"})).status(), 200);
}

#[test]
fn a_bad_screen_size_request_is_a_warning_and_a_failed_one_an_error() {
    let cp = CloudPhone::start();
    assert_eq!(cp.post_json("api/v1/display", &json!({"width": "360", "height": 780, "density": 160})).status(), 400);
    let refused = wait_record(&cp, "warning", "gateway", "Changement de résolution refusé", SOON);
    assert!(refused["text"].as_str().unwrap().contains("width, height and density are required"), "{refused}");
    assert!(refused["notify"].is_null(), "a refused request is not a toast: {refused}");

    cp.fake().control(json!({"fail_next": {"display": "set-resolution.sh: no space left"}}));
    assert_eq!(cp.post_json("api/v1/display", &json!({"width": 360, "height": 780, "density": 160})).status(), 202);
    let asked = wait_record(&cp, "normal", "gateway", "Changement de résolution demandé", SOON);
    assert_eq!(asked["notify"], true, "a requested reboot is a toast: {asked}");
    assert_eq!(asked["params"]["size"], "360×780");
    let failed = wait_record(&cp, "error", "gateway", "Échec du changement de résolution", SOON);
    assert_eq!(failed["notify"], true);
    let text = failed["text"].as_str().unwrap();
    assert!(text.contains("no space left") && text.contains("journalctl -u cloudphone-display"), "{failed}");
}

#[test]
fn an_applied_settings_change_restarts_android_with_normal_records() {
    let cp = CloudPhone::start();
    let token = cp.page_token();
    let response = cp.post_json("api/v1/emulator-settings", &json!({"renderer": "swiftshader", "cores": 2, "memoryMb": 4096}));
    assert_eq!(response.status(), 202, "{:?}", response.text());
    // The emulator restarts, the gateway follows it: the new one reports
    // the change applied and nothing as an error.
    cp.wait_new_token(&token, Duration::from_secs(30));
    cp.wait_for_android(Duration::from_secs(30));
    let done = wait_record(&cp, "normal", "gateway", "Changement des réglages d’Android appliqué", SOON);
    assert_eq!(done["notify"], true);
    std::thread::sleep(Duration::from_secs(4));
    let errors: Vec<Value> = records(&cp).into_iter().filter(|r| r["level"] == "error").collect();
    assert!(errors.is_empty(), "an asked restart is no error: {errors:?}");
}

#[test]
fn another_viewer_coming_and_going_are_notify_records() {
    let cp = CloudPhone::start();
    let first = Viewer::open(&cp, &viewer_id("first"));
    cp.wait_viewers("one viewer", Duration::from_secs(10), |n| n == 1);
    let second_id = viewer_id("second");
    let second = Viewer::open(&cp, &second_id);
    let came = wait_record(&cp, "normal", "gateway", "Un autre appareil s’est connecté", SOON);
    assert_eq!(came["notify"], true);
    assert_eq!(came["params"]["viewer"], second_id.as_str(), "the page that connected can tell it is itself");
    second.close();
    let left = wait_record(&cp, "normal", "gateway", "Un autre appareil s’est déconnecté", SOON);
    assert_eq!(left["notify"], true);
    drop(first);
}

#[test]
fn disconnecting_the_others_is_a_warning_with_notify() {
    let cp = CloudPhone::start();
    let _other = Viewer::open(&cp, &viewer_id("other"));
    cp.wait_viewers("the other viewer", Duration::from_secs(10), |n| n == 1);
    let me = viewer_id("me");
    assert_eq!(cp.post_json("api/v1/viewers/disconnect-others", &json!({"viewer": me})).status(), 200);
    let record = wait_record(&cp, "warning", "gateway", "Un appareil a déconnecté les autres (1)", SOON);
    assert_eq!(record["notify"], true);
}

#[test]
fn a_restarted_gateway_answers_an_old_cursor_with_its_own_records() {
    let cp = CloudPhone::start();
    let cursor = cp.get_json("api/v1/logs")["cursor"].as_str().unwrap().to_string();
    let token = cp.page_token();
    cp.fake().action("restart_gateway");
    cp.wait_new_token(&token, SOON);
    let after = cp.get_json(&format!("api/v1/logs?since={cursor}"));
    assert!(after["records"].as_array().unwrap().iter().any(|r| r["text"] == "Le gateway a démarré"), "{after}");
}
