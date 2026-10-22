//! Slayer Legend's mpw18 watchdog on the fake emulator, at its real pace (a
//! look every 15 s, a repair after 2 bad looks, the first 2 looks after the
//! gateway's start only observed). The fake plays a generic app under the
//! game's package (its "app" option: pidof, am start, the focus, Android's
//! crash dialog in dumpsys and uiautomator), shown as a picture the plugin
//! reads as the battle screen (the top bar's emerald, the bottom menu's
//! names) once it runs. The game's own time to start is the fake's
//! start_seconds; the timings measured are printed (--nocapture).
use cloudphone_e2e::browser::{blocking, browser_test, fr, Options};
use cloudphone_e2e::*;
use serde_json::{json, Value};
use std::time::{Duration, Instant};

const SLAYER_LEGEND: &str = "05-plugins/slayer-legend";
const PACKAGE: &str = "com.gear2.growslayer";
const ACTIVITY: &str = "com.google.firebase.MessagingUnityPlayerActivity";
const START_SECONDS: u64 = 8;
const RELAUNCH: &str = "-s emulator-5558 shell am start -n com.gear2.growslayer/com.google.firebase.MessagingUnityPlayerActivity \
                        -a android.intent.action.MAIN -c android.intent.category.LAUNCHER";

fn game(state: &str) -> Value {
    json!({"package": PACKAGE, "activity": ACTIVITY, "state": state, "start_seconds": START_SECONDS,
           "picture": [[0.36, 0.012, 0.42, 0.036, [40, 200, 60]], [0.0, 0.972, 1.0, 0.998, [225, 225, 225]]]})
}

fn with_game(state: &str) -> CloudPhone {
    CloudPhone::start_with(json!({"plugins": [SLAYER_LEGEND], "options": {"app": game(state)}}))
}

fn watchdog(cp: &CloudPhone) -> Value {
    cp.get_json("api/v1/plugins/slayer-legend/watchdog")
}

fn adb(cp: &CloudPhone) -> Vec<String> {
    cp.fake().record()["adb"].as_array().unwrap().iter().map(|c| c.as_str().unwrap().to_string()).collect()
}

fn relaunches(cp: &CloudPhone) -> usize {
    adb(cp).iter().filter(|c| c.contains("am start")).count()
}

fn plugin_records(cp: &CloudPhone) -> Vec<Value> {
    cp.get_json("api/v1/logs")["records"].as_array().unwrap().iter().filter(|r| r["source"] == "slayer-legend").cloned().collect()
}

fn has_record(cp: &CloudPhone, level: &str, text: &str, notify: bool) -> bool {
    plugin_records(cp).iter().any(|r| r["level"] == level && r["text"] == text && (r["notify"] == true) == notify)
}

/// Waits for the watchdog's look to say the game farms ("OK").
fn wait_ok(cp: &CloudPhone, timeout: Duration) {
    wait_for("the watchdog to say OK", timeout, || {
        let state = cp.try_get_json("api/v1/plugins/slayer-legend/watchdog")?;
        (state["status"]["template"] == "OK" && state["symptom"].is_null()).then_some(())
    });
}

fn wait_launch_done(cp: &CloudPhone, timeout: Duration) {
    wait_for("the relaunch to reach the battle screen", timeout, || {
        let launch = cp.try_get_json("api/v1/plugins/slayer-legend/launch")?;
        (launch["state"] == "done").then_some(())
    });
}

/// No command that could kill or reset the game.
fn never_killed(cp: &CloudPhone) {
    for call in adb(cp) {
        assert!(!call.contains(" -S") && !call.contains("force-stop") && !call.contains("kill") && !call.contains("pm clear"), "{call}");
    }
}

#[test]
fn a_crashed_game_is_closed_relaunched_and_farming_again_within_a_minute() {
    let cp = with_game("running");
    // The first two looks (15 s, 30 s) only observe; the game farms.
    wait_ok(&cp, Duration::from_secs(40));
    assert_eq!(relaunches(&cp), 0);
    let crash = Instant::now();
    cp.fake().control(json!({"app": {"state": "crashed"}}));
    wait_for("the relaunch", Duration::from_secs(45), || (relaunches(&cp) > 0).then_some(()));
    let relaunched = crash.elapsed();
    wait_launch_done(&cp, Duration::from_secs(45));
    let back = crash.elapsed();
    wait_ok(&cp, Duration::from_secs(25));
    let verified = crash.elapsed();
    eprintln!("crash → relaunch {:.1} s, → battle {:.1} s (the game's own start {START_SECONDS} s), → verified {:.1} s",
              relaunched.as_secs_f64(), back.as_secs_f64(), verified.as_secs_f64());
    assert!(relaunched <= Duration::from_secs(32), "detected in two looks: {relaunched:?}");
    assert!(back <= Duration::from_secs(60), "farming again within a minute: {back:?}");

    let calls = adb(&cp);
    assert!(calls.iter().any(|c| c == RELAUNCH), "{calls:#?}");
    assert!(calls.iter().any(|c| c.ends_with("shell uiautomator dump /dev/tty")), "{calls:#?}");
    // The tap on "Close app" (the fake's bounds: 8–92 % across, 50–56 % down
    // a 480×1040 screen), never on "App info" below it.
    let taps: Vec<(i64, i64)> = calls.iter().filter_map(|c| c.split("shell input tap ").nth(1))
        .map(|xy| { let v: Vec<i64> = xy.split(' ').map(|n| n.parse().unwrap()).collect(); (v[0], v[1]) }).collect();
    assert_eq!(taps.len(), 1, "{calls:#?}");
    let (x, y) = taps[0];
    assert!((38..=442).contains(&x) && (520..=582).contains(&y), "{taps:?}");
    never_killed(&cp);

    assert!(has_record(&cp, "warning", "Farming mpw18: the game crashed (Android's error window)", true), "{:#?}", plugin_records(&cp));
    assert!(has_record(&cp, "normal", "Repair: game relaunch", false), "{:#?}", plugin_records(&cp));
    assert!(has_record(&cp, "normal", "Repair done: game relaunch", false), "{:#?}", plugin_records(&cp));
    let counters = &watchdog(&cp)["counters"];
    assert_eq!(counters["next_attempt"], json!({}), "the relaunch worked: no backoff {counters}");
    assert_eq!(counters["alerts"], 1, "{counters}");
}

#[test]
fn a_game_not_responding_gets_wait_once_then_an_alert_and_is_never_killed() {
    let cp = with_game("running");
    wait_ok(&cp, Duration::from_secs(40));
    cp.fake().control(json!({"app": {"state": "anr"}}));
    wait_for("the alert", Duration::from_secs(40), || {
        has_record(&cp, "error", "Farming mpw18: the game is not responding (Android's window): Wait tapped with no effect", true)
            .then_some(())
    });
    std::thread::sleep(Duration::from_secs(16));
    let calls = adb(&cp);
    // One tap, on "Wait" (the fake's first button: 50–56 % down), never on
    // "Close app" below it (a kill), and no relaunch.
    let taps: Vec<(i64, i64)> = calls.iter().filter_map(|c| c.split("shell input tap ").nth(1))
        .map(|xy| { let v: Vec<i64> = xy.split(' ').map(|n| n.parse().unwrap()).collect(); (v[0], v[1]) }).collect();
    assert_eq!(taps.len(), 1, "{calls:#?}");
    assert!((520..=582).contains(&taps[0].1), "{taps:?}");
    assert_eq!(relaunches(&cp), 0, "{calls:#?}");
    assert!(has_record(&cp, "normal", "The game is not responding: Wait pressed", false), "{:#?}", plugin_records(&cp));
    assert_eq!(watchdog(&cp)["symptom"], "anr");
    never_killed(&cp);
}

#[test]
fn at_the_gateways_start_it_observes_then_relaunches_a_game_that_is_not_running() {
    let start = Instant::now();
    let cp = with_game("absent");
    wait_for("the watchdog's first look", Duration::from_secs(25), || {
        let state = cp.try_get_json("api/v1/plugins/slayer-legend/watchdog")?;
        (state["symptom"] == "not_running").then_some(())
    });
    // The second look alerts; the relaunch waits for the third (45 s).
    wait_for("the alert", Duration::from_secs(25), || {
        has_record(&cp, "warning", "Farming mpw18: the game is not running", true).then_some(())
    });
    assert_eq!(relaunches(&cp), 0, "a restored gateway observes its first two looks");
    wait_for("the relaunch", Duration::from_secs(30), || (relaunches(&cp) > 0).then_some(()));
    let relaunched = start.elapsed();
    wait_launch_done(&cp, Duration::from_secs(40));
    let back = start.elapsed();
    eprintln!("gateway start → relaunch {:.1} s, → battle {:.1} s (the game's own start {START_SECONDS} s)",
              relaunched.as_secs_f64(), back.as_secs_f64());
    assert!(relaunched >= Duration::from_secs(40), "not before the third look: {relaunched:?}");
    let calls = adb(&cp);
    assert_eq!(calls.iter().filter(|c| c.contains("am start")).collect::<Vec<_>>(), [RELAUNCH], "once, MAIN/LAUNCHER, no -S");
    never_killed(&cp);
    wait_ok(&cp, Duration::from_secs(25));
}

#[test]
fn free_play_suspends_it_and_another_holder_of_the_lease_defers_the_relaunch() {
    let cp = with_game("absent");
    let path = "api/v1/plugins/slayer-legend";
    assert_eq!(cp.post_json(&format!("{path}/mode"), &json!({"mode": "free"})).status(), 200);
    // Free play: the game may be on another device; nothing is checked.
    std::thread::sleep(Duration::from_secs(35));
    let state = watchdog(&cp);
    assert_eq!(state["status"]["template"], "Jeu libre : rien n’est surveillé", "{state}");
    assert_eq!(relaunches(&cp), 0);
    assert!(plugin_records(&cp).iter().all(|r| r["notify"] != true), "no alert in free play: {:#?}", plugin_records(&cp));

    let lease = json!({"holder": "agent", "reason": "réglages", "seconds": 600});
    assert_eq!(cp.post_json(&format!("{path}/lease"), &lease).status(), 200);
    assert_eq!(cp.post_json(&format!("{path}/mode"), &json!({"mode": "mpw18"})).status(), 200);
    wait_for("the deferred repair", Duration::from_secs(70), || {
        has_record(&cp, "normal", "Repair deferred: lease held by agent", false).then_some(())
    });
    assert_eq!(relaunches(&cp), 0, "deferred while the lease is held");
    assert_eq!(watchdog(&cp)["lease"]["holder"], "agent");
    let url = cp.url(&format!("{path}/lease"));
    let token = cp.page_token();
    let released = off_runtime(move || client().delete(url).header("X-CloudPhone-Token", token).json(&json!({"holder": "agent"}))
        .send().unwrap().status().as_u16());
    assert_eq!(released, 200);
    wait_for("the relaunch once released", Duration::from_secs(25), || (relaunches(&cp) > 0).then_some(()));
    wait_launch_done(&cp, Duration::from_secs(40));
    never_killed(&cp);
}

/// The game asking to sign in (its two buttons, as the plugin measured
/// them), with Google's chooser listing `accounts`.
fn signing_in(accounts: &[&str]) -> CloudPhone {
    let mut app = game("signin");
    app["sign_in_button"] = json!([0.245, 0.722, 0.755, 0.770]);
    app["accounts"] = json!(accounts);
    app["sign_in_picture"] = json!([
        [0.0, 0.0, 1.0, 1.0, [90, 60, 35]],
        [0.245, 0.722, 0.755, 0.770, [235, 235, 235]], [0.285, 0.738, 0.325, 0.756, [65, 131, 239]],
        [0.37, 0.742, 0.66, 0.752, [117, 117, 116]],
        [0.245, 0.788, 0.755, 0.836, [235, 235, 235]], [0.28, 0.802, 0.32, 0.822, [0, 0, 0]],
        [0.37, 0.808, 0.66, 0.818, [0, 0, 0]]]);
    CloudPhone::start_with(json!({"plugins": [SLAYER_LEGEND], "options": {"app": app}}))
}

fn taps(cp: &CloudPhone) -> Vec<(i64, i64)> {
    adb(cp).iter().filter_map(|c| c.split("shell input tap ").nth(1).map(str::to_string))
        .map(|xy| { let v: Vec<i64> = xy.split(' ').map(|n| n.parse().unwrap()).collect(); (v[0], v[1]) }).collect()
}

#[test]
fn the_sign_in_screen_gets_google_then_the_one_account_and_farms_again() {
    let cp = signing_in(&["player@example.com"]);
    // Observed, alerted, then the relaunch signs in.
    wait_launch_done(&cp, Duration::from_secs(120));
    wait_ok(&cp, Duration::from_secs(40));
    let taps = taps(&cp);
    // "Sign in with Google" (72–77 % down a 1040 px screen), then the account's row (40 % down).
    assert_eq!(taps.len(), 2, "{taps:?}");
    assert!((751..=800).contains(&taps[0].1), "Google's button: {taps:?}");
    assert!((416..=466).contains(&taps[1].1), "the account: {taps:?}");
    assert!(!taps.iter().any(|&(_, y)| (819..=870).contains(&y)), "never Apple's button: {taps:?}");
    assert!(has_record(&cp, "warning", "Farming mpw18: the game asks to sign in again (Sign in with Google)", true),
            "{:#?}", plugin_records(&cp));
    never_killed(&cp);
}

#[test]
fn a_chooser_with_two_accounts_is_for_the_user_and_never_tapped() {
    let cp = signing_in(&["player@example.com", "other@example.com"]);
    wait_for("the launch to stop", Duration::from_secs(120), || {
        let launch = cp.try_get_json("api/v1/plugins/slayer-legend/launch")?;
        (launch["state"] == "blocked").then_some(launch)
    });
    let launch = cp.get_json("api/v1/plugins/slayer-legend/launch");
    assert_eq!(launch["message_t"]["template"], "Reconnexion Google échouée : le sélecteur propose {count} comptes au lieu d’un", "{launch}");
    let taps = taps(&cp);
    assert_eq!(taps.len(), 1, "Google's button only: {taps:?}");
    never_killed(&cp);
}

#[test]
fn the_page_shows_the_watchdogs_look_in_the_modes_state_and_the_lease_in_debug() {
    let cp = with_game("running");
    let phone = cp.clone();
    browser_test(&cp, Options::without_video(), |page| async move {
        page.open_options().await;
        // No rows of its own: the end of the selected mode's État row.
        page.wait_dialog_value(fr::OPTIONS_PANEL, "État", Duration::from_secs(50), |v| v.starts_with("Farming mpw18") && v.ends_with(" · OK")).await;
        let text = page.dialog_text(fr::OPTIONS_PANEL).await;
        for gone in ["Surveillance mpw18", "Bail", "Prochains essais", "Réessayer"] {
            assert!(!text.lines().any(|l| l.trim() == gone), "no {gone:?} row: {text}");
        }
        let lease = json!({"holder": "agent", "reason": "réglages", "seconds": 600});
        let taken = blocking(move || phone.post_json("api/v1/plugins/slayer-legend/lease", &lease).status().as_u16());
        assert_eq!(taken, 200);
        // The lease is for the developer: in « Debug & développement », not in État.
        page.js("[...document.querySelectorAll('[role=dialog] summary')].find(s => s.innerText.trim() === 'Debug & développement').click()",
            vec![]).await;
        page.wait_dialog_value(fr::OPTIONS_PANEL, "Bail", Duration::from_secs(25), |v| v == "agent (réglages)").await;
        let state = page.dialog_value(fr::OPTIONS_PANEL, "État").await.unwrap_or_default();
        assert!(state.ends_with(" · OK"), "{state}");
    });
}
