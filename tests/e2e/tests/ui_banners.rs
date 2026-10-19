//! Every status the page shows (role=status): the messages that cover the
//! screen while something is wrong, and the closable banners while it works
//! but worse than usual; and the colour of the LED on ↻ that goes with them
//! (red: needs action, orange: being fixed, green: fine). The states come
//! from the fake emulator: no real phone is crashed, stopped or kicked.
//!
//! One test per branch of the page's diagnose() (example/src/diagnose.ts),
//! in its order, and for the edges just below its thresholds:
//! - server unreachable (2 missed polls): `server_unreachable_…`; one missed
//!   poll says nothing: `one_missed_state_poll_shows_nothing`
//! - kicked: `a_page_kicked_by_another_device_…`
//! - screen size change pending / applying: `a_screen_size_change_on_its_way_…`,
//!   `a_screen_size_change_being_applied_…`
//! - settings change pending / applying: `an_android_settings_change_on_its_way_…`,
//!   `an_android_settings_change_being_applied_…`
//! - unit failed, auto-restart, inactive, deactivating, activating:
//!   `an_emulator_stopped_on_an_error_…`, `an_emulator_crash_with_an_automatic_restart_…`,
//!   `a_stopped_emulator_…`, `a_stopping_emulator_unit_…`, `a_starting_emulator_unit_…`
//! - Android booting, with / before the video: `android_still_booting_…`,
//!   `android_booting_before_the_video_…`
//! - Android not answering, with / before the video:
//!   `an_emulator_that_does_not_answer_says_…`,
//!   `an_emulator_that_does_not_answer_before_the_video_…`
//! - video dropped: `a_dropped_stream_…`
//! - video not connected after 15 s (nothing but "connecting" until 14 s):
//!   `a_video_that_never_connects_says_so_after_15_seconds`
//! - touches failing (3 failed requests, not 2): `touches_that_fail_…`,
//!   `two_failed_touch_requests_show_nothing_yet`
//! - other viewers (1, then 2), not while the video connects:
//!   `another_viewer_makes_the_watching_banner_count_it`,
//!   `another_viewer_is_not_reported_while_the_video_connects`
//! - server overloaded (not at load = threads): `heavy_load_…`
//! - all well: `a_healthy_phone_shows_no_status`
use cloudphone_e2e::browser::{blocking, browser_test, en, fr, led, Options, Page};
use cloudphone_e2e::*;
use serde_json::json;
use std::time::Duration;

const SOON: Duration = Duration::from_secs(20);

/// The banner's first line for `others` other viewers.
fn watching(others: u64) -> String {
    if others == 1 {
        "Un autre appareil regarde ce téléphone".to_string()
    } else {
        format!("{others} autres appareils regardent ce téléphone")
    }
}

/// Asserts the status `text` (with `detail`) is shown, covering the screen
/// or as a closable banner, with the LED's colour.
async fn expect_status(page: &Page, text: &str, detail: Option<&str>, covers: bool, colour: &str) {
    let shown = page.wait_status(text, SOON).await;
    if let Some(detail) = detail {
        assert!(shown.contains(detail), "{text:?} comes with {detail:?}: {shown:?}");
    }
    assert_eq!(page.status_is_closable(text).await, !covers, "{text:?} {}", if covers { "covers the screen" } else { "is a closable banner" });
    page.wait_led(colour, Duration::from_secs(5)).await;
}

/// Asserts no status contains `text` at any moment during `duration`.
async fn never_status(page: &Page, text: &str, duration: Duration) {
    let start = std::time::Instant::now();
    while start.elapsed() < duration {
        let shown = page.banners().await;
        assert!(!shown.iter().any(|b| b.contains(text)), "{text:?} shown: {shown:?}");
        page.sleep(Duration::from_millis(200)).await;
    }
}

/// Waits until the gateway's GET /api/v1/state has `value` at `pointer`.
fn wait_gateway_state(phone: &CloudPhone, pointer: &str, value: &str) {
    let start = std::time::Instant::now();
    loop {
        let state = phone.get_json("api/v1/state");
        if state.pointer(pointer).and_then(|v| v.as_str()) == Some(value) {
            return;
        }
        assert!(start.elapsed() < SOON, "state {pointer} never {value:?}: {state}");
        std::thread::sleep(Duration::from_millis(200));
    }
}

#[test]
fn server_unreachable_covers_the_screen_and_clears_when_it_answers_again() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        phone.fake().action("stop_gateway");
        expect_status(&page, "Serveur injoignable", Some("Vérifiez que le VPN (WireGuard) est connecté sur cet appareil."), true, led::RED).await;
        phone.fake().action("start_gateway");
        page.wait_no_status("Serveur injoignable", SOON).await;
        // The video comes back by itself.
        page.wait_js("the video playing again", Duration::from_secs(60),
            "const l = document.querySelector('[aria-label^=\"Connexion \"]'); return !!l && l.getAttribute('aria-label') === 'Connexion connected'", vec![]).await;
        page.wait_led(led::GREEN, SOON).await;
    });
}

#[test]
fn a_page_kicked_by_another_device_says_so_and_reload_takes_it_back() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        let other = phone.clone();
        let taker = blocking(move || {
            let taker = Viewer::open(&other, &viewer_id("taker"));
            other.wait_viewers("the page and the taker", Duration::from_secs(10), |n| n == 2);
            let response = other.post_json("api/v1/viewers/disconnect-others", &json!({"viewer": taker.id}));
            assert_eq!(response.status(), 200);
            taker
        });
        expect_status(&page, "Un autre appareil a pris la main", Some("Touchez ↻ pour la reprendre."), true, led::RED).await;
        // The page does not try to reconnect by itself.
        page.sleep(Duration::from_secs(4)).await;
        assert_eq!(phone.viewers(), 1, "only the taker watches");
        page.click_label(fr::RECONNECT).await;
        page.wait_for_video(Duration::from_secs(45)).await;
        page.wait_no_status("pris la main", SOON).await;
        let p = phone.clone();
        blocking(move || p.wait_viewers("the page back as a new viewer, beside the taker", Duration::from_secs(15), |n| n == 2));
        blocking(move || taker.close());
    });
}

#[test]
fn a_screen_size_change_on_its_way_covers_the_screen() {
    let cp = CloudPhone::start_with(json!({"options": {"hold_requests": true}}));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        let response = phone.post_json("api/v1/display", &json!({"width": 360, "height": 780, "density": 160}));
        assert_eq!(response.status(), 202);
        expect_status(&page, "Changement de résolution", Some("Android redémarre…"), true, led::ORANGE).await;
    });
}

#[test]
fn an_android_settings_change_on_its_way_covers_the_screen() {
    let cp = CloudPhone::start_with(json!({"settings": {"cores": 2}, "options": {"hold_requests": true}}));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        let response = phone.post_json("api/v1/emulator-settings", &json!({"renderer": "lavapipe", "cores": 2, "memoryMb": 2048}));
        assert_eq!(response.status(), 202);
        expect_status(&page, "Changement des réglages d’Android", Some("Android redémarre…"), true, led::ORANGE).await;
        // The root service takes it: applying, Android restarts, done.
        phone.fake().control(json!({"hold_requests": false}));
        page.wait_no_status("Changement des réglages", Duration::from_secs(60)).await;
        page.wait_led(led::GREEN, Duration::from_secs(60)).await;
    });
}

#[test]
fn an_emulator_stopped_on_an_error_covers_the_screen_in_red() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        phone.fake().control(json!({"unit": {"active": "failed", "sub": "failed", "result": "exit-code"}}));
        expect_status(&page, "Android s’est arrêté sur une erreur", Some("Il ne redémarre pas tout seul : il faut le relancer sur le serveur."), true, led::RED).await;
    });
}

#[test]
fn an_emulator_crash_with_an_automatic_restart_says_it_restarts() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        phone.fake().control(json!({"unit": {"active": "activating", "sub": "auto-restart", "result": "exit-code", "restarts": 1}}));
        expect_status(&page, "Android a planté", Some("Redémarrage automatique…"), true, led::ORANGE).await;
    });
}

#[test]
fn a_stopped_emulator_covers_the_screen_in_red() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        phone.fake().control(json!({"unit": {"active": "inactive", "sub": "dead"}}));
        expect_status(&page, "Android est arrêté", Some("Il faut le démarrer sur le serveur."), true, led::RED).await;
    });
}

#[test]
fn a_starting_emulator_unit_says_android_starts() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        phone.fake().control(json!({"unit": {"active": "activating", "sub": "start"}}));
        expect_status(&page, "Android démarre…", None, true, led::ORANGE).await;
    });
}

#[test]
fn android_still_booting_is_a_banner_over_a_playing_video() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        phone.fake().control(json!({"booted": false}));
        expect_status(&page, "Android démarre…", Some("Cela peut prendre une minute."), false, led::ORANGE).await;
        phone.fake().control(json!({"booted": true}));
        page.wait_no_status("Android démarre…", SOON).await;
        page.wait_led(led::GREEN, SOON).await;
    });
}

#[test]
fn android_booting_before_the_video_covers_the_screen() {
    let cp = CloudPhone::start_with(json!({"booted": false, "options": {"offer": false}}));
    browser_test(&cp, Options::without_video(), |page| async move {
        expect_status(&page, "Android démarre…", Some("Cela peut prendre une minute."), true, led::ORANGE).await;
    });
}

#[test]
fn an_emulator_that_does_not_answer_says_the_server_reconnects() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        phone.fake().control(json!({"grpc": "down"}));
        expect_status(&page, "Le serveur se reconnecte à Android…", None, false, led::ORANGE).await;
        phone.fake().control(json!({"grpc": "up"}));
        page.wait_no_status("Le serveur se reconnecte", SOON).await;
    });
}

#[test]
fn a_dropped_stream_says_video_interrupted_then_reconnects_by_itself() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        let sessions = phone.fake().record()["sessions"].as_array().unwrap().len();
        phone.fake().control(json!({"action": "drop_streams", "bye": true}));
        expect_status(&page, "Vidéo interrompue", Some("Reconnexion…"), true, led::ORANGE).await;
        page.wait_no_status("Vidéo interrompue", Duration::from_secs(30)).await;
        page.wait_led(led::GREEN, Duration::from_secs(30)).await;
        let after = phone.fake().record()["sessions"].as_array().unwrap().len();
        assert_eq!(after, sessions + 1, "one new session, opened by the page itself");
    });
}

#[test]
fn a_stream_lost_without_notice_is_noticed_and_reconnected() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        // The emulator side vanishes: no bye, the peer connection just ends.
        phone.fake().control(json!({"action": "drop_streams", "bye": false}));
        page.wait_js("the stream to be noticed as lost", Duration::from_secs(40),
            "const l = document.querySelector('[aria-label^=\"Connexion \"]'); return !!l && l.getAttribute('aria-label') !== 'Connexion connected'", vec![]).await;
        page.wait_led(led::GREEN, Duration::from_secs(60)).await;
    });
}

#[test]
fn a_video_that_never_connects_says_so_after_15_seconds() {
    let cp = CloudPhone::start_with(json!({"options": {"offer": false}}));
    browser_test(&cp, Options::without_video(), |page| async move {
        page.wait_status("Connexion au flux…", SOON).await;
        // Connecting, nothing wrong yet: only that message up to 14 s
        // (counted from the page's start, a little before the stream's).
        let started = page.js("return performance.now()", vec![]).await.as_f64().unwrap();
        never_status(&page, "La vidéo ne se connecte pas",
            Duration::from_millis((14_000.0 - started).max(0.0) as u64)).await;
        assert_eq!(page.banners().await, vec!["Connexion au flux…".to_string()]);
        let shown = page.wait_status("La vidéo ne se connecte pas", Duration::from_secs(30)).await;
        assert!(shown.contains("Le réseau bloque peut-être le flux vidéo (UDP). Touchez ↻ pour réessayer."), "{shown:?}");
        assert!(!page.status_is_closable("La vidéo ne se connecte pas").await);
        page.wait_led(led::RED, Duration::from_secs(5)).await;
    });
}

#[test]
fn touches_that_fail_show_a_red_banner() {
    // No data channel: touches go over HTTP, and Android refuses them.
    let cp = CloudPhone::start_with(json!({"options": {"data_channels": false, "touch_fails": true}}));
    browser_test(&cp, Options::default(), |page| async move {
        let (x, y) = page.viewport_point((480, 1040), 240, 520).await;
        for _ in 0..3 {
            page.click_at(x, y).await;
            page.sleep(Duration::from_millis(300)).await;
        }
        expect_status(&page, "Les touches n’arrivent pas à Android", None, false, led::RED).await;
    });
}

#[test]
fn another_viewer_makes_the_watching_banner_count_it() {
    let cp = CloudPhone::start();
    let first = Viewer::open(&cp, &viewer_id("banner-a"));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        expect_status(&page, &watching(1), Some("L’image peut être plus lente."), false, led::GREEN).await;
        let p = phone.clone();
        let second = blocking(move || Viewer::open(&p, &viewer_id("banner-b")));
        page.wait_status(&watching(2), SOON).await;
        blocking(move || second.close());
        page.wait_status(&watching(1), SOON).await;
    });
    first.close();
}

#[test]
fn the_watching_banner_goes_when_the_other_viewer_leaves() {
    let cp = CloudPhone::start();
    let first = Viewer::open(&cp, &viewer_id("leave"));
    browser_test(&cp, Options::default(), |page| async move {
        page.wait_status(&watching(1), SOON).await;
        blocking(move || first.close());
        page.wait_no_status("regarde", SOON).await;
        assert!(page.banners().await.is_empty());
    });
}

#[test]
fn a_closed_banner_stays_closed_until_its_message_changes() {
    let cp = CloudPhone::start();
    let first = Viewer::open(&cp, &viewer_id("close-a"));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        let text = watching(1);
        page.wait_status(&text, SOON).await;
        page.close_banner(&text).await;
        page.wait_no_status(&text, Duration::from_secs(3)).await;
        // Several state polls later, the same message stays closed.
        page.sleep(Duration::from_secs(8)).await;
        assert!(!page.banners().await.iter().any(|b| b.contains(&text)), "closed banner came back: {:?}", page.banners().await);
        // A new message (one more viewer) brings it back.
        let p = phone.clone();
        let second = blocking(move || Viewer::open(&p, &viewer_id("close-b")));
        page.wait_status(&watching(2), SOON).await;
        blocking(move || second.close());
    });
    first.close();
}

#[test]
fn the_banner_cross_is_labelled_for_screen_readers() {
    let cp = CloudPhone::start_with(json!({"load": 50.0}));
    browser_test(&cp, Options::default(), |page| async move {
        page.wait_status("Serveur très chargé", SOON).await;
        let labels = page.js("return [...document.querySelectorAll('[role=status] button')].map(b => b.getAttribute('aria-label'))", vec![]).await;
        assert!(!labels.as_array().unwrap().is_empty() && labels.as_array().unwrap().iter().all(|l| l == fr::CLOSE), "every banner cross says {:?}: {labels}", fr::CLOSE);
    });
}

#[test]
fn heavy_load_shows_a_banner_while_the_video_plays() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        let cpus = phone.get_json("api/v1/state")["load"]["cpus"].as_f64().unwrap();
        // Exactly as many tasks as threads is not "heavy".
        phone.fake().control(json!({"load": cpus}));
        page.sleep(Duration::from_secs(5)).await;
        assert!(page.banners().await.is_empty(), "load = threads: {:?}", page.banners().await);
        phone.fake().control(json!({"load": cpus + 0.5}));
        expect_status(&page, "Serveur très chargé", Some("L’image peut ralentir."), false, led::GREEN).await;
        phone.fake().control(json!({"load": 0.2}));
        page.wait_no_status("Serveur très chargé", SOON).await;
    });
}

#[test]
fn the_most_important_message_wins() {
    // Heavy load and another viewer are minor next to a crashed Android.
    let cp = CloudPhone::start_with(json!({"load": 50.0}));
    let other = Viewer::open(&cp, &viewer_id("minor"));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        page.wait_status(&watching(1), SOON).await;
        phone.fake().control(json!({"unit": {"active": "failed", "sub": "failed"}}));
        page.wait_status("Android s’est arrêté sur une erreur", SOON).await;
        let shown = page.banners().await;
        assert_eq!(shown.len(), 1, "one message at a time: {shown:?}");
    });
    other.close();
}

#[test]
fn statuses_are_translated_for_an_english_browser() {
    let cp = CloudPhone::start_with(json!({"load": 50.0}));
    let phone = cp.clone();
    browser_test(&cp, Options::english_browser(), |page| async move {
        page.wait_status("Server under heavy load", SOON).await;
        assert!(page.has_label(en::CLOSE).await, "the cross says Close");
        phone.fake().action("stop_gateway");
        page.wait_status("Server unreachable", SOON).await;
    });
}

#[test]
fn a_screen_size_change_being_applied_covers_the_screen() {
    // The root service takes the request and stays on "applying".
    let cp = CloudPhone::start_with(json!({"options": {"apply_seconds": 120}}));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        let response = phone.post_json("api/v1/display", &json!({"width": 360, "height": 780, "density": 160}));
        assert_eq!(response.status(), 202);
        let p = phone.clone();
        blocking(move || wait_gateway_state(&p, "/display/state", "applying"));
        expect_status(&page, "Changement de résolution", Some("Android redémarre…"), true, led::ORANGE).await;
    });
}

#[test]
fn an_android_settings_change_being_applied_covers_the_screen() {
    let cp = CloudPhone::start_with(json!({"settings": {"cores": 2}, "options": {"apply_seconds": 120}}));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        let response = phone.post_json("api/v1/emulator-settings", &json!({"renderer": "lavapipe", "cores": 2, "memoryMb": 2048}));
        assert_eq!(response.status(), 202);
        let p = phone.clone();
        blocking(move || wait_gateway_state(&p, "/settings/state", "applying"));
        expect_status(&page, "Changement des réglages d’Android", Some("Android redémarre…"), true, led::ORANGE).await;
    });
}

#[test]
fn a_stopping_emulator_unit_covers_the_screen_in_red() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        phone.fake().control(json!({"unit": {"active": "deactivating", "sub": "stop-sigterm"}}));
        expect_status(&page, "Android est arrêté", Some("Il faut le démarrer sur le serveur."), true, led::RED).await;
    });
}

#[test]
fn an_emulator_that_does_not_answer_before_the_video_covers_the_screen() {
    // No video ever (no offer); the gateway starts with Android up, then
    // loses it.
    let cp = CloudPhone::start_with(json!({"options": {"offer": false}}));
    let phone = cp.clone();
    browser_test(&cp, Options::without_video(), |page| async move {
        phone.fake().control(json!({"grpc": "down"}));
        expect_status(&page, "Le serveur se reconnecte à Android…", None, true, led::ORANGE).await;
    });
}

#[test]
fn a_healthy_phone_shows_no_status() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::default(), |page| async move {
        // Two state polls and more.
        page.sleep(Duration::from_secs(7)).await;
        assert!(page.banners().await.is_empty(), "{:?}", page.banners().await);
        page.wait_led(led::GREEN, Duration::from_secs(5)).await;
    });
}

#[test]
fn one_missed_state_poll_shows_nothing() {
    // The page polls the state every 3 s and gives up on a poll after 4 s.
    // Stalling the gateway from just after a poll (at a) until a + 7.5 s
    // makes the poll at a + 3 time out at a + 7 and the one at a + 6
    // answer at a + 7.5: one missed poll, never two in a row.
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        page.js("performance.clearResourceTimings()", vec![]).await;
        let since = page.wait_js("a state poll just answered", SOON,
            "const now = performance.now(); \
             const e = performance.getEntriesByType('resource').filter(e => e.name.includes('/api/v1/state?')).pop(); \
             return e && now - e.responseEnd < 300 ? now - e.startTime : null", vec![]).await;
        let since = since.as_f64().unwrap() / 1000.0;
        assert!(since < 1.0, "the poll took {since} s");
        let p = phone.clone();
        blocking(move || p.fake().control(json!({"action": "pause_gateway", "seconds": 7.5 - since - 0.1})));
        never_status(&page, "Serveur injoignable", Duration::from_secs(11)).await;
        // The polls answer again after the stall.
        let answered = page.js(
            "return performance.getEntriesByType('resource').filter(e => e.name.includes('/api/v1/state?')).length", vec![]).await;
        assert!(answered.as_u64().unwrap() >= 3, "state polls answered: {answered}");
    });
}

#[test]
fn two_failed_touch_requests_show_nothing_yet() {
    // One click is two requests over HTTP (press, release), both refused.
    let cp = CloudPhone::start_with(json!({"options": {"data_channels": false, "touch_fails": true}}));
    browser_test(&cp, Options::default(), |page| async move {
        let (x, y) = page.viewport_point((480, 1040), 240, 520).await;
        page.click_at(x, y).await;
        never_status(&page, "Les touches n’arrivent pas à Android", Duration::from_secs(3)).await;
        page.click_at(x, y).await;
        page.wait_status("Les touches n’arrivent pas à Android", SOON).await;
    });
}

#[test]
fn another_viewer_is_not_reported_while_the_video_connects() {
    let cp = CloudPhone::start_with(json!({"options": {"offer": false}}));
    let other = Viewer::open(&cp, &viewer_id("connecting"));
    let phone = cp.clone();
    browser_test(&cp, Options::without_video(), |page| async move {
        page.wait_status("Connexion au flux…", SOON).await;
        let p = phone.clone();
        blocking(move || p.wait_viewers("the page and the other viewer", Duration::from_secs(10), |n| n == 2));
        // A state poll later, still well before the 15 s message.
        never_status(&page, "regarde", Duration::from_millis(3500)).await;
        assert_eq!(page.banners().await, vec!["Connexion au flux…".to_string()]);
    });
    other.close();
}
