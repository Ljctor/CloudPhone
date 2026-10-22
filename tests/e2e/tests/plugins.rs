//! The plugin host, as the gateway serves it (`--plugins_dir`): the list,
//! the plugins' page modules, their routes under /api/v1/plugins/<id>/
//! behind the same checks as the rest of the API, and what a plugin's
//! gateway code may use (a screenshot shared between calls, adb). With test plugins from
//! tests/fake-emulator/plugins, nothing game-specific.
use cloudphone_e2e::*;
use serde_json::{json, Value};
use std::time::{Duration, Instant};

const PROBE: &str = "tests/fake-emulator/plugins/e2e-probe";
const BROKEN: &str = "tests/fake-emulator/plugins/e2e-broken";
const MISNAMED: &str = "tests/fake-emulator/plugins/e2e-misnamed";
const FUTURE: &str = "tests/fake-emulator/plugins/e2e-future";
const SLAYER_LEGEND: &str = "05-plugins/slayer-legend";

fn with(plugins: Value) -> CloudPhone {
    CloudPhone::start_with(json!({"plugins": plugins}))
}

fn post_without_token(cp: &CloudPhone, path: &str, origin: Option<&str>) -> u16 {
    let url = cp.url(path);
    let origin = origin.map(String::from);
    off_runtime(move || {
        let mut request = client().post(url).json(&json!({}));
        if let Some(origin) = origin {
            request = request.header("Origin", origin);
        }
        request.send().unwrap().status().as_u16()
    })
}

#[test]
fn without_plugins_the_list_is_empty() {
    let cp = CloudPhone::start();
    let list = cp.get("api/v1/plugins");
    assert_eq!(list.headers()["cache-control"], "no-store");
    assert_eq!(list.json().unwrap(), json!({"plugins": []}));
    assert_eq!(cp.get("api/v1/plugins/e2e-probe/hello").status(), 404);
}

#[test]
fn an_installed_plugin_is_listed_with_its_page_module() {
    let cp = with(json!([PROBE]));
    assert_eq!(
        cp.get_json("api/v1/plugins"),
        json!({"plugins": [{"id": "e2e-probe", "title": "Sonde e2e", "version": "1.2.3", "page": "/plugins/e2e-probe/page.js"}]})
    );
}

#[test]
fn the_plugins_top_level_scripts_are_served_and_nothing_else() {
    let cp = with(json!([PROBE]));
    for script in ["page.js", "helper.js"] {
        let response = cp.get(&format!("plugins/e2e-probe/{script}"));
        assert_eq!(response.status(), 200, "{script}");
        let kind = response.headers()["content-type"].to_str().unwrap().to_string();
        assert!(kind.starts_with("text/javascript"), "{script}: {kind}");
    }
    for other in ["gateway.py", "plugin.json", "missing.js", "sub/page.js"] {
        assert_eq!(cp.get(&format!("plugins/e2e-probe/{other}")).status(), 404, "{other} is not served");
    }
}

#[test]
fn a_plugins_get_route_answers_under_its_prefix() {
    let cp = with(json!([PROBE]));
    let response = cp.get("api/v1/plugins/e2e-probe/hello");
    assert_eq!(response.headers()["cache-control"], "no-store");
    assert_eq!(response.json().unwrap(), json!({"plugin": "e2e-probe", "prefix": "/api/v1/plugins/e2e-probe"}));
}

#[test]
fn a_plugins_post_route_needs_the_page_token_and_the_pages_origin() {
    let cp = with(json!([PROBE]));
    assert_eq!(post_without_token(&cp, "api/v1/plugins/e2e-probe/count", None), 403, "no token");
    assert_eq!(post_without_token(&cp, "api/v1/plugins/e2e-probe/count", Some("http://elsewhere.example")), 403, "foreign origin");
    assert_eq!(cp.get_json("api/v1/plugins/e2e-probe/count")["count"], 0, "refused POSTs did nothing");
    let response = cp.post_json("api/v1/plugins/e2e-probe/count", &json!({"by": 2}));
    assert_eq!(response.status(), 200);
    assert_eq!(response.json().unwrap()["count"], 2);
}

#[test]
fn a_plugin_reads_androids_screen() {
    let cp = CloudPhone::start_with(json!({"plugins": [PROBE], "display": {"width": 360, "height": 780, "density": 160}}));
    assert_eq!(cp.get_json("api/v1/plugins/e2e-probe/screen"), json!({"screen": [360, 780], "bytes": 360 * 780 * 3}));
    cp.fake().control(json!({"grpc": "down"}));
    std::thread::sleep(Duration::from_millis(300));
    // plugins.py documents context.screenshot() as "(width, height, RGB888
    // bytes), or None": with the emulator down it must give None, not raise
    // (found by this test: the gRPC error reaches the plugin, HTTP 500).
    let response = cp.get("api/v1/plugins/e2e-probe/screen");
    assert_eq!(response.status(), 200, "the plugin's route still answers with the emulator down");
    assert_eq!(response.json().unwrap(), json!({"screen": null}), "no emulator: no screenshot, no error");
}

#[test]
fn a_plugin_runs_adb_on_the_emulator() {
    let cp = with(json!([PROBE]));
    let response = cp.post_json("api/v1/plugins/e2e-probe/home", &json!({}));
    assert_eq!(response.json().unwrap(), json!({"code": 0}));
    let key = cp.fake().wait_record("HOME through adb", Duration::from_secs(5), |r| r["keys"].as_array()?.last().cloned());
    assert_eq!(key, json!({"key": "HOME", "via": "adb", "time": key["time"]}));
    let adb = cp.fake().record()["adb"].clone();
    assert!(adb.as_array().unwrap().iter().any(|l| l == "-s emulator-5558 shell input keyevent HOME"), "on the emulator's serial: {adb}");
}

#[test]
fn a_broken_or_misnamed_plugin_is_skipped_and_the_others_work() {
    let cp = with(json!([PROBE, BROKEN, {"path": MISNAMED, "name": "e2e-misnamed"}]));
    let list = cp.get_json("api/v1/plugins");
    let ids: Vec<&str> = list["plugins"].as_array().unwrap().iter().map(|p| p["id"].as_str().unwrap()).collect();
    // The broken plugin only fails in the browser: the gateway lists it.
    assert_eq!(ids, ["e2e-broken", "e2e-probe"], "a plugin whose id is not its directory's name is not loaded: {list}");
    assert_eq!(cp.get("plugins/another-name/page.js").status(), 404);
    assert_eq!(cp.get_json("api/v1/plugins/e2e-probe/hello")["plugin"], "e2e-probe");
    assert_eq!(cp.get("api/v1/ping").status(), 204, "the gateway still answers");
}

#[test]
fn a_plugin_reads_a_1080p_screen() {
    // 1080×2340 RGB888 is 7.6 MB, above gRPC's default 4 MiB receive limit.
    let cp = CloudPhone::start_with(json!({"plugins": [PROBE], "display": {"width": 1080, "height": 2340, "density": 480}}));
    let response = cp.get("api/v1/plugins/e2e-probe/screen");
    assert_eq!(response.status(), 200, "the 1080p screenshot reaches the plugin: {:?}", response.text());
    assert_eq!(response.json().unwrap(), json!({"screen": [1080, 2340], "bytes": 1080 * 2340 * 3}));
}

fn captures(cp: &CloudPhone) -> Value {
    cp.get_json("api/v1/state?details=1")["plugins"]["e2e-probe"]["screenshots"].clone()
}

#[test]
fn plugin_calls_within_max_age_share_one_screenshot() {
    let cp = with(json!([PROBE]));
    assert_eq!(captures(&cp), 0, "counted per plugin from the start");
    for _ in 0..2 {
        let shot = cp.get_json("api/v1/plugins/e2e-probe/screen?max_age=30");
        assert_eq!(shot["screen"], json!([480, 1040]));
    }
    assert_eq!(captures(&cp), 1, "the second call within max_age reuses the first capture");
    cp.get_json("api/v1/plugins/e2e-probe/screen");
    assert_eq!(captures(&cp), 2, "without max_age, a new capture");
    // The plugin's own touch makes earlier captures stale; then two calls
    // at once share the capture under way.
    assert_eq!(cp.post_json("api/v1/plugins/e2e-probe/home", &json!({})).status(), 200);
    let calls: Vec<_> = (0..2)
        .map(|_| {
            let url = cp.url("api/v1/plugins/e2e-probe/screen?max_age=30");
            std::thread::spawn(move || client().get(url).send().unwrap().json::<Value>().unwrap())
        })
        .collect();
    for call in calls {
        assert_eq!(call.join().unwrap()["screen"], json!([480, 1040]));
    }
    assert_eq!(captures(&cp), 3, "after a touch: one new capture for both calls");
}

#[test]
fn a_plugins_analysis_does_not_hold_the_gateway() {
    let cp = with(json!([PROBE]));
    assert_eq!(cp.get("api/v1/state").status(), 200);
    // The probe's analysis sleeps 2 s in context.analyse.
    let url = cp.url("api/v1/plugins/e2e-probe/analyse?seconds=2");
    let analysis = std::thread::spawn(move || {
        let answer = client().get(url).send().unwrap().json::<Value>().unwrap();
        (answer, Instant::now())
    });
    std::thread::sleep(Duration::from_millis(500));
    let asked = Instant::now();
    let state = cp.get("api/v1/state");
    let answered = Instant::now();
    assert_eq!(state.status(), 200);
    let (answer, analysed) = analysis.join().unwrap();
    assert_eq!(answer, json!({"slept": 2.0}));
    assert!(answered < analysed, "the state was asked while the analysis ran");
    let took = answered - asked;
    assert!(took < Duration::from_millis(700), "GET /api/v1/state took {took:?} during a 2 s analysis");
}

#[test]
fn slayer_legends_mode_and_mine_come_back_after_a_gateway_restart() {
    // Only routes that need no game screen: the mode, its timer, the mine's
    // floor and area, the highest stage. Kept in the plugin's data directory.
    let cp = with(json!([SLAYER_LEGEND]));
    let until = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs_f64() + 3600.0;
    let set = cp.post_json(
        "api/v1/plugins/slayer-legend/mode",
        &json!({"mode": "mine", "until": until, "floor": 12, "area": 3, "stage18": 40}),
    );
    assert_eq!(set.status(), 200, "{:?}", set.text());
    assert_eq!(cp.get_json("api/v1/plugins/slayer-legend/stages?known=45")["highest"], 45);
    let before = cp.get_json("api/v1/plugins/slayer-legend/mode");
    assert_eq!(before["mine"]["enabled"], true, "{before}");

    let token = cp.page_token();
    cp.fake().action("restart_gateway");
    cp.wait_new_token(&token, Duration::from_secs(20));
    let after = cp.get_json("api/v1/plugins/slayer-legend/mode");
    for key in ["mode", "until", "stage18", "configured"] {
        assert_eq!(after[key], before[key], "{key}: {after}");
    }
    for key in ["enabled", "floor", "area", "until"] {
        assert_eq!(after["mine"][key], before["mine"][key], "mine {key}: {after}");
    }
    assert_eq!(after["mine"]["state"], "waiting", "the mine watches again: {after}");
    assert_eq!(cp.get_json("api/v1/plugins/slayer-legend/stages")["highest"], 45);
    // Turned off, it stays off across the next restart.
    assert_eq!(cp.post_json("api/v1/plugins/slayer-legend/mode", &json!({"mode": "mpw18"})).status(), 200);
    let token = cp.page_token();
    cp.fake().action("restart_gateway");
    cp.wait_new_token(&token, Duration::from_secs(20));
    let off = cp.get_json("api/v1/plugins/slayer-legend/mode");
    assert_eq!((off["mode"].clone(), off["mine"]["enabled"].clone()), (json!("mpw18"), json!(false)), "{off}");
    // A timer that ends while the gateway is down: the mine and its mode
    // come back over, not running.
    let soon = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs_f64() + 1.0;
    let set = cp.post_json("api/v1/plugins/slayer-legend/mode", &json!({"mode": "mine", "until": soon, "floor": 7, "area": 1}));
    assert_eq!(set.json().unwrap()["mine"]["enabled"], true);
    std::thread::sleep(Duration::from_millis(1500));
    let token = cp.page_token();
    cp.fake().action("restart_gateway");
    cp.wait_new_token(&token, Duration::from_secs(20));
    let ended = cp.get_json("api/v1/plugins/slayer-legend/mode");
    assert_eq!(ended["mode"], "mpw18", "{ended}");
    assert_eq!(ended["until"], Value::Null, "{ended}");
    assert_eq!(ended["mine"]["enabled"], false, "{ended}");
    assert_ne!(ended["mine"]["state"], "waiting", "the mine does not watch again: {ended}");
}

#[test]
fn a_plugin_for_another_api_is_refused_and_listed_with_its_error() {
    let cp = with(json!([PROBE, FUTURE]));
    let list = cp.get_json("api/v1/plugins");
    let plugins = list["plugins"].as_array().unwrap();
    assert_eq!(plugins.len(), 2, "{list}");
    let future = &plugins[0];
    assert_eq!(future["id"], "e2e-future", "{list}");
    assert_eq!(future["title"], "Greffon futur");
    assert!(future.get("page").is_none(), "no page module for the page to import: {future}");
    let error = future["error"].as_str().unwrap_or_default();
    assert!(error.contains("API 2"), "the error says why: {error}");
    assert_eq!(cp.get("api/v1/plugins/e2e-future/hello").status(), 404, "its gateway code did not run");
    assert_eq!(cp.get("plugins/e2e-future/page.js").status(), 404, "its scripts are not served");
    assert_eq!(plugins[1]["id"], "e2e-probe");
    assert!(plugins[1].get("error").is_none(), "{list}");
    assert_eq!(cp.get_json("api/v1/plugins/e2e-probe/hello")["plugin"], "e2e-probe");
}

#[test]
fn slayer_legends_timed_modes_start_with_30_minutes() {
    // A timed mode chosen without an end time gets 30 minutes; one with an
    // end time keeps it; mpw18 has none.
    let cp = with(json!([SLAYER_LEGEND]));
    let now = || std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs_f64();
    for mode in ["mpw4", "free", "mine"] {
        assert_eq!(cp.post_json("api/v1/plugins/slayer-legend/mode", &json!({"mode": "mpw18"})).status(), 200);
        let asked = now();
        let set = cp.post_json("api/v1/plugins/slayer-legend/mode", &json!({"mode": mode, "floor": 7, "area": 2, "stage4": 31}));
        assert_eq!(set.status(), 200, "{mode}: {:?}", set.text());
        let answer = cp.get_json("api/v1/plugins/slayer-legend/mode");
        assert_eq!(answer["mode"], mode, "{answer}");
        assert_eq!(answer["gold"], Value::Null, "the gold scroll is unknown off the battle screen: {answer}");
        let left = answer["until"].as_f64().unwrap_or_else(|| panic!("{mode}: no timer: {answer}")) - asked;
        assert!((1795.0..1805.0).contains(&left), "{mode}: {left} s left: {answer}");
    }
    let until = now() + 600.0;
    cp.post_json("api/v1/plugins/slayer-legend/mode", &json!({"mode": "mpw18"}));
    cp.post_json("api/v1/plugins/slayer-legend/mode", &json!({"mode": "free", "until": until}));
    let kept = cp.get_json("api/v1/plugins/slayer-legend/mode")["until"].as_f64().unwrap();
    assert!((kept - until).abs() < 0.01, "an end time given is kept: {kept} for {until}");
    cp.post_json("api/v1/plugins/slayer-legend/mode", &json!({"mode": "mpw18"}));
    assert_eq!(cp.get_json("api/v1/plugins/slayer-legend/mode")["until"], Value::Null);
}

#[test]
fn slayer_legend_refuses_a_mode_not_configured_yet() {
    // mpw4 without its stage, the mine without its floor or area: 400 with
    // the reason in French, and the mode stays as it was.
    let cp = with(json!([SLAYER_LEGEND]));
    for (body, reason) in [
        (json!({"mode": "mpw4"}), "Farming mpw4 : choisis d’abord son stage"),
        (json!({"mode": "mine", "area": 2}), "Mine fermée : choisis d’abord l’étage (1 à 9999) et la zone (1 à 5)"),
        (json!({"mode": "mine", "floor": 12}), "Mine fermée : choisis d’abord l’étage (1 à 9999) et la zone (1 à 5)"),
    ] {
        let refused = cp.post_json("api/v1/plugins/slayer-legend/mode", &body);
        assert_eq!(refused.status(), 400, "{body}");
        assert_eq!(refused.json().unwrap(), json!({"error": reason}), "{body}");
        assert_eq!(cp.get_json("api/v1/plugins/slayer-legend/mode")["mode"], "mpw18", "{body}");
    }
}

#[test]
fn slayer_legend_keeps_a_value_a_post_leaves_null_or_out() {
    // A browser that does not know a value (after a gateway restart, for
    // instance) sends it null or not at all: the gateway's stays.
    let cp = with(json!([SLAYER_LEGEND]));
    let set = cp.post_json("api/v1/plugins/slayer-legend/mode", &json!({"mode": "mpw18", "stage18": 920, "stage4": 31}));
    assert_eq!(set.status(), 200, "{:?}", set.text());
    let set = cp.post_json("api/v1/plugins/slayer-legend/mode", &json!({"mode": "mpw18", "stage18": null}));
    assert_eq!(set.status(), 200, "{:?}", set.text());
    let answer = cp.get_json("api/v1/plugins/slayer-legend/mode");
    assert_eq!((answer["stage18"].clone(), answer["stage4"].clone()), (json!(920), json!(31)), "{answer}");
    // mpw4 is configured on the gateway: chosen without its stage.
    let set = cp.post_json("api/v1/plugins/slayer-legend/mode", &json!({"mode": "mpw4", "stage4": null}));
    assert_eq!(set.status(), 200, "{:?}", set.text());
    let answer = cp.get_json("api/v1/plugins/slayer-legend/mode");
    assert_eq!((answer["mode"].clone(), answer["stage4"].clone()), (json!("mpw4"), json!(31)), "{answer}");
}

#[test]
fn slayer_legend_keeps_a_timer_a_post_leaves_out_and_clears_a_null_one() {
    let cp = with(json!([SLAYER_LEGEND]));
    let now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs_f64();
    let mode = "api/v1/plugins/slayer-legend/mode";
    cp.post_json(mode, &json!({"mode": "mine", "floor": 7, "area": 2, "until": now + 600.0}));
    // The same mode posted again without until: its timer stays.
    assert_eq!(cp.post_json(mode, &json!({"mode": "mine", "floor": 8})).status(), 200);
    let answer = cp.get_json(mode);
    assert!((answer["until"].as_f64().unwrap() - (now + 600.0)).abs() < 0.01, "{answer}");
    // An explicit null: no time limit (the mine farms until stopped).
    assert_eq!(cp.post_json(mode, &json!({"mode": "mine", "until": null})).status(), 200);
    let answer = cp.get_json(mode);
    assert_eq!((answer["mode"].clone(), answer["until"].clone()), (json!("mine"), Value::Null), "{answer}");
}

#[test]
fn slayer_legends_stages_are_its_loadouts() {
    // POST /mode's stages land in the modes' loadouts, which GET /mode reads
    // back; POST /loadout keeps what it leaves out.
    let cp = with(json!([SLAYER_LEGEND]));
    assert_eq!(cp.post_json("api/v1/plugins/slayer-legend/mode", &json!({"mode": "mpw18", "stage18": 920, "stage4": 31})).status(), 200);
    let loadouts = cp.get_json("api/v1/plugins/slayer-legend/loadout")["loadouts"].clone();
    assert_eq!((loadouts["mpw18"]["stage"].clone(), loadouts["mpw4"]["stage"].clone()), (json!(920), json!(31)), "{loadouts}");
    let set = cp.post_json("api/v1/plugins/slayer-legend/loadout", &json!({"mode": "mpw4", "stage": 41, "preset": "II"}));
    assert_eq!(set.status(), 200, "{:?}", set.text());
    assert_eq!(cp.get_json("api/v1/plugins/slayer-legend/mode")["stage4"], 41);
    let token = cp.page_token();
    cp.fake().action("restart_gateway");
    cp.wait_new_token(&token, Duration::from_secs(20));
    let loadouts = cp.get_json("api/v1/plugins/slayer-legend/loadout")["loadouts"].clone();
    assert_eq!(loadouts["mpw4"], json!({"stage": 41, "preset": "II", "soul_weapon": null, "weapon": null, "placeable": null}));
    assert_eq!(cp.get_json("api/v1/plugins/slayer-legend/mode")["stage18"], 920);
}

fn delete_lease(cp: &CloudPhone, holder: &str, token: bool) -> u16 {
    let (url, page_token, body) = (cp.url("api/v1/plugins/slayer-legend/lease"), cp.page_token(), json!({"holder": holder}));
    off_runtime(move || {
        let mut request = client().delete(url).json(&body);
        if token {
            request = request.header("X-CloudPhone-Token", page_token);
        }
        request.send().unwrap().status().as_u16()
    })
}

#[test]
fn slayer_legends_lease_needs_the_page_token_and_only_its_holder_releases_it() {
    let cp = with(json!([SLAYER_LEGEND]));
    let path = "api/v1/plugins/slayer-legend/lease";
    assert_eq!(cp.get_json(path)["lease"], Value::Null);
    assert_eq!(post_without_token(&cp, path, None), 403, "POST without the token");
    let taken = cp.post_json(path, &json!({"holder": "agent", "reason": "réglages", "seconds": 600}));
    assert_eq!(taken.status(), 200, "{:?}", taken.text());
    let lease = cp.get_json(path)["lease"].clone();
    assert_eq!((lease["holder"].clone(), lease["reason"].clone()), (json!("agent"), json!("réglages")), "{lease}");
    let ttl = lease["until"].as_f64().unwrap() - lease["since"].as_f64().unwrap();
    assert!((599.0..=601.0).contains(&ttl), "{lease}");
    let other = cp.post_json(path, &json!({"holder": "someone", "reason": "x", "seconds": 60}));
    assert_eq!(other.status(), 409, "another holder waits");
    assert_eq!(other.json().unwrap()["error"], "bail tenu par agent");
    assert_eq!(delete_lease(&cp, "agent", false), 403, "DELETE without the token");
    assert_eq!(delete_lease(&cp, "someone", true), 404, "not its lease");
    assert_eq!(cp.get_json(path)["lease"]["holder"], "agent");
    assert_eq!(delete_lease(&cp, "agent", true), 200);
    assert_eq!(cp.get_json(path)["lease"], Value::Null);
}

/// POST with a phone alert's one-time action token, without the page token
/// and, as ntfy's http action sends it, without an Origin header.
fn post_with_action_token(cp: &CloudPhone, path: &str, token: &str, body: &Value) -> u16 {
    post_with_action_token_from(cp, path, token, None, body)
}

/// The same, with an Origin header when origin is given.
fn post_with_action_token_from(cp: &CloudPhone, path: &str, token: &str, origin: Option<&str>, body: &Value) -> u16 {
    let (url, token, body, origin) = (cp.url(path), token.to_string(), body.clone(), origin.map(String::from));
    off_runtime(move || {
        let mut request = client().post(url).header("X-CloudPhone-Action", token).json(&body);
        if let Some(origin) = origin {
            request = request.header("Origin", origin);
        }
        request.send().unwrap().status().as_u16()
    })
}

/// The plugin with the game running, in front (the fake's app option).
fn with_the_game_in_front() -> CloudPhone {
    let app = json!({"package": "com.gear2.growslayer", "activity": "com.google.firebase.MessagingUnityPlayerActivity",
        "state": "running", "picture": [[0.36, 0.012, 0.42, 0.036, [40, 200, 60]], [0.0, 0.972, 1.0, 0.998, [225, 225, 225]]]});
    CloudPhone::start_with(json!({"plugins": [SLAYER_LEGEND], "options": {"app": app}}))
}

#[test]
fn slayer_legends_switch_is_not_held_by_an_input_with_the_game_away() {
    // No game: the launcher has the focus, so a touch is not playing.
    let cp = with(json!([SLAYER_LEGEND]));
    let mode = "api/v1/plugins/slayer-legend/mode";
    assert_eq!(cp.post_json("api/v1/notify", &json!({"enabled": true})).status(), 200);
    assert_eq!(cp.post_json("api/v1/input", &json!({})).status(), 200);
    assert_eq!(cp.post_json(mode, &json!({"mode": "mpw4", "stage4": 31})).status(), 200);
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(8) {
        let answer = cp.get_json(mode);
        assert!(answer["hold"].is_null(), "no hold with the game away: {answer}");
        std::thread::sleep(Duration::from_millis(500));
    }
    assert!(!cp.fake().ntfy_posts().iter().any(|p| p["text"].as_str().is_some_and(|t| t.contains("en attente"))));
}

#[test]
fn slayer_legends_switch_on_hold_while_the_user_plays_alerts_once_with_one_time_buttons() {
    let cp = with_the_game_in_front();
    let (mode, hold) = ("api/v1/plugins/slayer-legend/mode", "api/v1/plugins/slayer-legend/mode/hold");
    assert_eq!(cp.post_json("api/v1/notify", &json!({"enabled": true})).status(), 200);
    assert_eq!(cp.post_json(hold, &json!({"action": "resume"})).status(), 409, "nothing on hold");
    // The user plays: the switch to mpw4 waits for the end of their minute.
    assert_eq!(cp.post_json("api/v1/input", &json!({})).status(), 200);
    assert_eq!(cp.post_json(mode, &json!({"mode": "mpw4", "stage4": 31})).status(), 200);
    let held = wait_for("the switch on hold", Duration::from_secs(20), || {
        let answer = cp.try_get_json(mode)?;
        (!answer["hold"].is_null()).then_some(answer)
    });
    assert_eq!((held["hold"]["mode"].clone(), held["setup"].clone()), (json!("mpw4"), json!(true)), "{held}");
    let left = held["hold"]["left"].as_u64().unwrap();
    assert!((40..=60).contains(&left), "{held}");
    // One alert, with the real delay and its two buttons.
    let alert = wait_for("the hold's alert", Duration::from_secs(10), || {
        cp.fake().ntfy_posts().into_iter().find(|p| p["text"].as_str().is_some_and(|t| t.contains("en attente")))
    });
    let text = alert["text"].as_str().unwrap().to_string();
    assert!(text.starts_with("Passage au farming mpw4 en attente : tu joues. Nouvel essai dans ") && text.ends_with(" s."), "{text}");
    let actions = alert["headers"]["Actions"].as_str().unwrap().to_string();
    let buttons: Vec<&str> = actions.split("; ").collect();
    assert_eq!(buttons.len(), 2, "{actions}");
    assert!(buttons[0].starts_with("http, 'Passer en jeu libre', 'http://"), "{actions}");
    assert!(buttons[1].starts_with("http, 'Reprendre maintenant', 'http://"), "{actions}");
    let id = held["hold"]["id"].as_str().unwrap();
    for (button, action) in buttons.iter().zip(["free", "resume"]) {
        assert!(button.contains("/api/v1/plugins/slayer-legend/mode/hold', method='POST', "), "{button}");
        assert!(button.contains(&format!("body='{{\"action\":\"{action}\",\"hold\":\"{id}\"}}'")), "{button}");
    }
    assert!(!actions.contains(&cp.page_token()), "never the page token: {actions}");
    let token = actions.split("headers.X-CloudPhone-Action='").nth(1).unwrap().split('\'').next().unwrap().to_string();
    assert_eq!(post_with_action_token(&cp, hold, "not-a-token", &json!({"action": "resume"})), 403);
    assert_eq!(post_with_action_token(&cp, mode, &token, &json!({"mode": "free"})), 403, "only its own path");
    // A foreign page's POST is refused, even with the token, which it does not spend.
    let body = json!({"action": "resume", "hold": id});
    assert_eq!(post_with_action_token_from(&cp, hold, &token, Some("https://example.org"), &body), 403, "foreign Origin");
    assert_eq!(cp.get_json(mode)["hold"]["id"], id, "still on hold");
    // « Reprendre maintenant » from the phone (ntfy sends no Origin): the
    // switch runs now, once.
    assert_eq!(post_with_action_token(&cp, hold, &token, &body), 200, "no Origin, a valid token");
    assert_eq!(post_with_action_token(&cp, hold, &token, &json!({"action": "resume", "hold": id})), 403, "spent");
    let resumed = wait_for("the switch resumed", Duration::from_secs(20), || {
        let answer = cp.try_get_json(mode)?;
        (answer["hold"].is_null() && answer["state"] != "waiting").then_some(answer)
    });
    assert_eq!(resumed["mode"], "mpw4", "{resumed}");
    // The same answer again changes nothing; another one finds nothing on hold.
    assert_eq!(cp.post_json(hold, &json!({"action": "resume"})).status(), 200);
    assert_eq!(cp.post_json(hold, &json!({"action": "free"})).status(), 409);
    assert_eq!(cp.post_json(hold, &json!({"action": "later"})).status(), 400);
    let alerts: Vec<Value> = cp.fake().ntfy_posts().into_iter()
        .filter(|p| p["text"].as_str().is_some_and(|t| t.contains("en attente"))).collect();
    assert_eq!(alerts.len(), 1, "one alert: {alerts:?}");
}
