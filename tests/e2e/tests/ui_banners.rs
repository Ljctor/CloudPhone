//! Every status the page shows (role=status): the messages that cover the
//! screen while something is wrong, and the closable banners while it works
//! but worse than usual; and the colour of the LED on ↻ that goes with them
//! (red: needs action, orange: being fixed, green: fine). The states come
//! from the fake emulator: no real phone is crashed, stopped or kicked.
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
