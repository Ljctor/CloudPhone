//! The gateway's log (GET /api/v1/logs): one stream of records {time,
//! level, source, text, notify?}, levels normal, warning and error, a
//! cursor to read only new ones. Failures forced on the fake emulator
//! (emulator gone, adb offline or never answering, a bad or failing
//! screen size request) must give records of the right level, errors
//! saying what to do next; events worth the user's attention carry notify
//! (a mark only: the page pops nothing up, phone alerts go through ntfy).
//! Records are also kept in files (--log_dir): they outlive a gateway
//! restart, filters read them beyond memory, old files are gzipped and
//! expired ones deleted, and a disk that refuses writes is one warning.
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
    let start = all.iter().find(|r| r["text"].as_str().unwrap().starts_with("Gateway started")).expect("the gateway's start");
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
    let record = wait_record(&cp, "error", "emulator", "Android crashed", SOON);
    assert_eq!(record["notify"], true, "{record}");
    assert!(record["text"].as_str().unwrap().contains("restart it on the server"), "says what to do: {record}");
    assert!(record.get("template").is_none(), "English, never translated: {record}");
}

#[test]
fn an_emulator_that_stops_on_an_error_is_an_error_record() {
    let cp = CloudPhone::start();
    cp.fake().control(json!({"unit": {"active": "failed", "sub": "failed", "result": "exit-code"}}));
    let record = wait_record(&cp, "error", "emulator", "Android stopped on an error (exit-code)", SOON);
    assert!(record["text"].as_str().unwrap().contains("It does not restart by itself: restart it on the server"), "{record}");
    assert_eq!(record["notify"], true);
}

#[test]
fn adb_offline_is_an_error_record_and_its_return_a_normal_one() {
    let cp = CloudPhone::start_with(json!({"options": {"adb_fails": true}}));
    assert_eq!(cp.post_json("api/v1/emulator/key", &json!({"key": "GoHome"})).status(), 500);
    let record = wait_record(&cp, "error", "adb", "adb no longer reaches Android", SOON);
    assert_eq!(record["notify"], true, "{record}");
    assert!(record["text"].as_str().unwrap().contains("not found"), "adb's reason: {record}");
    assert!(record["text"].as_str().unwrap().contains("restart it on the server"), "{record}");
    // Said once while it lasts.
    assert_eq!(cp.post_json("api/v1/emulator/key", &json!({"key": "GoHome"})).status(), 500);
    let offline = records(&cp).iter().filter(|r| r["source"] == "adb" && r["level"] == "error").count();
    assert_eq!(offline, 1);
    cp.fake().control(json!({"adb_fails": false}));
    assert_eq!(cp.post_json("api/v1/emulator/key", &json!({"key": "GoHome"})).status(), 200);
    wait_record(&cp, "normal", "adb", "adb reaches Android again", SOON);
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
    let refused = wait_record(&cp, "warning", "gateway", "Screen size change refused", SOON);
    assert!(refused["text"].as_str().unwrap().contains("width, height and density are required"), "{refused}");
    assert!(refused["notify"].is_null(), "a refused request carries no notify: {refused}");

    cp.fake().control(json!({"fail_next": {"display": "set-resolution.sh: no space left"}}));
    assert_eq!(cp.post_json("api/v1/display", &json!({"width": 360, "height": 780, "density": 160})).status(), 202);
    let asked = wait_record(&cp, "normal", "gateway", "Screen size change requested", SOON);
    assert_eq!(asked["notify"], true, "a requested reboot carries notify: {asked}");
    assert_eq!(asked["params"]["size"], "360×780");
    let failed = wait_record(&cp, "error", "gateway", "Screen size change failed", SOON);
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
    let done = wait_record(&cp, "normal", "gateway", "Android settings change applied", SOON);
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
    let came = wait_record(&cp, "normal", "gateway", "Another device connected", SOON);
    assert_eq!(came["notify"], true);
    assert_eq!(came["params"]["viewer"], second_id.as_str(), "the page that connected can tell it is itself");
    second.close();
    let left = wait_record(&cp, "normal", "gateway", "Another device disconnected", SOON);
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
    let record = wait_record(&cp, "warning", "gateway", "A device disconnected the others (1)", SOON);
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
    assert!(after["records"].as_array().unwrap().iter().any(|r| r["text"].as_str().unwrap().starts_with("Gateway started")), "{after}");
}

fn now() -> f64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs_f64()
}

fn starts(records: &[Value]) -> Vec<&Value> {
    records.iter().filter(|r| r["text"].as_str().unwrap().starts_with("Gateway started")).collect()
}

#[test]
fn records_survive_a_gateway_restart_and_each_start_names_its_release() {
    let cp = CloudPhone::start();
    assert_eq!(cp.post_json("api/v1/display", &json!({"width": "360", "height": 780, "density": 160})).status(), 400);
    let refused = wait_record(&cp, "warning", "gateway", "Screen size change refused", SOON);
    let token = cp.page_token();
    cp.fake().action("restart_gateway");
    cp.wait_new_token(&token, SOON);
    let all = wait_for("both gateway starts", SOON, || {
        let all = records(&cp);
        (starts(&all).len() == 2).then_some(all)
    });
    assert!(all.contains(&refused), "the record from before the restart is still served: {all:#?}");
    let version = std::fs::read_to_string(cloudphone_e2e::fake::repo_root().join("VERSION")).unwrap().trim().to_string();
    for start in starts(&all) {
        assert_eq!(start["text"], format!("Gateway started · version {version} · commit e2e0commit"), "{start}");
        assert_eq!((&start["params"]["version"], &start["params"]["commit"]), (&json!(version), &json!("e2e0commit")));
    }
    assert!(cp.fake().log_files().iter().any(|f| f.starts_with("records-") && f.ends_with(".jsonl")), "{:?}", cp.fake().log_files());
}

#[test]
fn filters_select_records_and_read_the_files_beyond_memory() {
    // 600 records from three hours ago in a file: memory keeps the last 500
    // of them, the first 100 are only on disk.
    let base = now() - 3.0 * 3600.0;
    let old: Vec<Value> = (0..600).map(|i| {
        let level = if i % 100 == 0 { "error" } else if i % 10 == 0 { "warning" } else { "normal" };
        let source = if i % 2 == 0 { "emulator" } else { "slayer-legend" };
        json!({"time": base + i as f64, "level": level, "source": source, "text": format!("Old record {i}")})
    }).collect();
    let cp = CloudPhone::start_with(json!({"log_files": [
        {"name": "records-20260101T000000Z.jsonl", "age_days": 0.1, "records": old}]}));
    let get = |query: &str| -> Value {
        let response = cp.get(&format!("api/v1/logs?{query}"));
        assert_eq!(response.status(), 200, "{query}");
        response.json().unwrap()
    };
    let texts = |answer: &Value| -> Vec<String> {
        answer["records"].as_array().unwrap().iter().map(|r| r["text"].as_str().unwrap().to_string()).collect()
    };
    // Without filters: the last 500 kept in memory, the oldest of which came from the file.
    let plain = records(&cp);
    assert!(plain.len() <= 500 && plain.iter().any(|r| r["text"] == "Old record 599"), "{}", plain.len());
    assert!(!plain.iter().any(|r| r["text"] == "Old record 0"));

    // since: from the file too, oldest first.
    let since = get(&format!("since={}&limit=5000", base - 1.0));
    let all = texts(&since);
    assert_eq!(all.iter().filter(|t| t.starts_with("Old record ")).count(), 600, "{all:?}");
    assert_eq!(all[0], "Old record 0");
    assert!(since["more"].is_null());
    assert!(since["cursor"].as_str().unwrap().contains('-'));
    // until, level (a minimum), source, contains (any case), limit (the newest).
    let range = texts(&get(&format!("since={}&until={}", base - 1.0, base + 9.5)));
    assert_eq!(range, (0..10).map(|i| format!("Old record {i}")).collect::<Vec<_>>());
    let errors = texts(&get(&format!("since={}&level=error&source=emulator", base - 1.0)));
    assert_eq!(errors, (0..6).map(|i| format!("Old record {}", i * 100)).collect::<Vec<_>>());
    let warnings = get(&format!("since={}&level=warning&until={}", base - 1.0, base + 600.0));
    assert_eq!(texts(&warnings).len(), 60);
    let some = texts(&get(&format!("since={}&source=slayer-legend&contains=RECORD%2015", base - 1.0)));
    assert_eq!(some, ["Old record 15", "Old record 151", "Old record 153", "Old record 155", "Old record 157", "Old record 159"]);
    let newest = get(&format!("since={}&until={}&limit=3", base - 1.0, base + 600.0));
    assert_eq!(texts(&newest), ["Old record 597", "Old record 598", "Old record 599"]);
    assert_eq!(newest["more"], true);
    // Without since, the files are read until limit records match.
    let first = texts(&get("contains=old%20record%201&level=error"));
    assert_eq!(first, ["Old record 100"]);
    // A limit above the maximum is lowered to it; bad values are refused.
    assert!(get("since=0&limit=100000")["records"].as_array().unwrap().len() <= 5000);
    for bad in ["level=fatal", "limit=0", "limit=many", "since=1&until=never"] {
        let response = cp.get(&format!("api/v1/logs?{bad}"));
        assert_eq!(response.status(), 400, "{bad}");
        assert!(response.json().unwrap()["error"].is_string());
    }
    // The page's polling: a cursor still gives only new records, filters
    // apply to them.
    let cursor = get("level=warning&limit=1")["cursor"].as_str().unwrap().to_string();
    assert_eq!(get(&format!("cursor={cursor}&level=warning"))["records"], json!([]));
    assert_eq!(cp.post_json("api/v1/display", &json!({"width": 361, "height": 780, "density": 160})).status(), 400);
    let new = get(&format!("cursor={cursor}&level=warning"));
    assert_eq!(texts(&new).len(), 1, "{new}");
    assert_eq!(get(&format!("cursor={cursor}&level=error"))["records"], json!([]));
}

#[test]
fn old_files_are_gzipped_and_expired_ones_deleted() {
    let at = |days: f64| json!([{"time": now() - days * 86400.0, "level": "normal", "source": "gateway", "text": format!("Written {days} days ago")}]);
    let cp = CloudPhone::start_with(json!({"log_files": [
        {"name": "records-20260801T000000Z.jsonl.gz", "age_days": 70, "records": at(70.0), "gzip": true},
        {"name": "records-20260802T000000Z.jsonl", "age_days": 62, "records": at(62.0)},
        {"name": "records-20260901T000000Z.jsonl.gz", "age_days": 40, "records": at(40.0), "gzip": true},
        {"name": "records-20261020T000000Z.jsonl", "age_days": 2, "records": at(2.0)},
        {"name": "records-29990101T000000Z.jsonl", "age_days": 0.01, "records": at(0.01)}]}));
    let files = wait_for("the files maintained", SOON, || {
        let files = cp.fake().log_files();
        (!files.iter().any(|f| f.contains("2026080")) && files.iter().any(|f| f == "records-20261020T000000Z.jsonl.gz"))
            .then_some(files)
    });
    assert!(files.contains(&"records-20260901T000000Z.jsonl.gz".to_string()), "kept for 61 days: {files:?}");
    assert!(files.contains(&"records-29990101T000000Z.jsonl".to_string()), "a recent file stays plain: {files:?}");
    assert!(!files.contains(&"records-20261020T000000Z.jsonl".to_string()), "{files:?}");
    // A gzipped file is still read.
    let answer = cp.get_json(&format!("api/v1/logs?since={}&contains=days%20ago", now() - 100.0 * 86400.0));
    let texts: Vec<&str> = answer["records"].as_array().unwrap().iter().map(|r| r["text"].as_str().unwrap()).collect();
    assert_eq!(texts, ["Written 40 days ago", "Written 2 days ago", "Written 0.01 days ago"]);
}

#[test]
fn a_disk_that_refuses_writes_is_one_warning_and_records_stay_in_memory() {
    let cp = CloudPhone::start_with(json!({"log_dir": "read-only"}));
    let warning = wait_record(&cp, "warning", "gateway", "Log records are no longer written to disk", SOON);
    assert!(warning["text"].as_str().unwrap().contains("Permission denied"), "{warning}");
    assert_eq!(cp.post_json("api/v1/display", &json!({"width": 361, "height": 780, "density": 160})).status(), 400);
    wait_record(&cp, "warning", "gateway", "Screen size change refused", SOON);
    let failures = records(&cp).iter().filter(|r| r["text"].as_str().unwrap().contains("no longer written to disk")).count();
    assert_eq!(failures, 1);
    assert!(cp.get("api/v1/ping").status().is_success());
    assert!(cp.fake().log_files().is_empty());
}
