//! The page in a real browser: video, toolbar, status LED, ping and fps.
use cloudphone_e2e::browser::{self, blocking, browser_test, en, fr, leading_number, led, Options};
use cloudphone_e2e::*;
use serde_json::json;
use std::time::Duration;

const SOON: Duration = Duration::from_secs(20);

#[test]
fn the_video_plays_and_its_time_advances() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::default(), |page| async move {
        let first = page.video().await;
        assert!(first["w"].as_u64().unwrap() > 0 && first["h"].as_u64().unwrap() > 0, "decoded frames: {first}");
        assert_eq!(first["paused"], false, "{first}");
        page.sleep(Duration::from_secs(3)).await;
        let later = page.video().await;
        let advanced = later["t"].as_f64().unwrap() - first["t"].as_f64().unwrap();
        assert!(advanced > 2.0, "currentTime advances with the clock: {first} -> {later}");
    });
}

#[test]
fn the_video_has_the_size_android_runs_at() {
    let cp = CloudPhone::start();
    let display = cp.get_json("api/v1/display");
    browser_test(&cp, Options::default(), |page| async move {
        let video = page.video().await;
        let (w, h) = (video["w"].as_u64().unwrap(), video["h"].as_u64().unwrap());
        let (rw, rh) = (display["running"]["width"].as_u64().unwrap(), display["running"]["height"].as_u64().unwrap());
        // The stream may be scaled, never reshaped.
        let ratio = (w as f64 / h as f64) / (rw as f64 / rh as f64);
        assert!((ratio - 1.0).abs() < 0.02, "stream {w}x{h} has Android's shape {rw}x{rh}");
    });
}

#[test]
fn the_page_lays_out_a_screen_of_another_shape_without_distortion() {
    // A tablet-like Android screen: the page must follow the size the
    // gateway reports, not the default phone shape.
    let cp = CloudPhone::start_with(json!({"display": {"width": 720, "height": 1152, "density": 320}}));
    browser_test(&cp, Options::default(), |page| async move {
        let video = page.video().await;
        assert_eq!((video["w"].as_u64().unwrap(), video["h"].as_u64().unwrap()), (720, 1152), "{video}");
        let surface = page.rect(&browser::css_label(fr::TOUCH_SURFACE)).await;
        let shown = surface["w"].as_f64().unwrap() / surface["h"].as_f64().unwrap();
        assert!((shown / (720.0 / 1152.0) - 1.0).abs() < 0.02, "the touch surface has Android's shape: {surface}");
    });
}

#[test]
fn the_video_is_shown_whole_and_undistorted_in_the_window() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::default(), |page| async move {
        let video = page.video().await;
        let window = page.js("return [innerWidth, innerHeight]", vec![]).await;
        let (vw, vh) = (window[0].as_f64().unwrap(), window[1].as_f64().unwrap());
        let (x, y, w, h) = (video["x"].as_f64().unwrap(), video["y"].as_f64().unwrap(), video["cssW"].as_f64().unwrap(), video["cssH"].as_f64().unwrap());
        assert!(x >= -0.5 && y >= -0.5 && x + w <= vw + 0.5 && y + h <= vh + 0.5, "video {video} inside the window {window}");
        let shown = w / h;
        let stream = video["w"].as_f64().unwrap() / video["h"].as_f64().unwrap();
        assert!((shown / stream - 1.0).abs() < 0.03, "displayed {w}x{h} keeps the stream's shape: {video}");
        // The toolbar does not cover the screen.
        let nav = page.rect("nav").await;
        let (nx, ny, nw, nh) = (nav["x"].as_f64().unwrap(), nav["y"].as_f64().unwrap(), nav["w"].as_f64().unwrap(), nav["h"].as_f64().unwrap());
        let overlap_x = (x + w).min(nx + nw) - x.max(nx);
        let overlap_y = (y + h).min(ny + nh) - y.max(ny);
        assert!(overlap_x <= 1.0 || overlap_y <= 1.0, "toolbar {nav} does not overlap the video {video}");
    });
}

#[test]
fn the_toolbar_has_every_button_with_its_french_label() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        let labels = page.toolbar_labels().await;
        let expected = [
            fr::POWER, fr::VOLUME_DOWN, fr::VOLUME_UP, fr::INFO, fr::RECENTS, fr::HOME, fr::BACK,
            fr::OPTIONS, fr::RECONNECT, fr::FULLSCREEN,
        ];
        assert_eq!(labels, expected, "toolbar buttons, in order");
        for label in expected {
            assert!(page.label_visible(label).await, "{label:?} is visible");
        }
        assert!(!page.has_label(fr::FOLD).await, "no fold button outside fullscreen");
    });
}

#[test]
fn the_screen_and_controls_are_named_landmarks() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        for label in [fr::SCREEN, fr::TOUCH_SURFACE, fr::CONTROLS, fr::NAVIGATION] {
            assert!(page.has_label(label).await, "an element labelled {label:?}");
        }
        assert_eq!(page.js("return document.querySelector('nav').getAttribute('aria-label')", vec![]).await, json!(fr::CONTROLS));
        assert_eq!(page.js("return document.documentElement.lang", vec![]).await, json!("fr"), "the document says it is French");
        // The navigation group holds recents, home and back.
        let nav = page
            .js(&format!("return [...document.querySelector('{}').querySelectorAll('button')].map(b => b.getAttribute('aria-label'))", browser::css_label(fr::NAVIGATION)), vec![])
            .await;
        assert_eq!(nav, json!([fr::RECENTS, fr::HOME, fr::BACK]));
    });
}

#[test]
fn the_led_turns_green_once_the_stream_is_connected() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::default(), |page| async move {
        page.wait_led(led::GREEN, Duration::from_secs(20)).await;
        assert_eq!(page.led().await["label"], "Connexion connected");
        let inside = page
            .js(&format!("return !!document.querySelector('{} [aria-label^=\"Connexion \"]')", browser::css_label(fr::RECONNECT)), vec![])
            .await;
        assert_eq!(inside, json!(true), "the LED sits on the reconnect button");
        assert!(page.banners().await.is_empty(), "nothing to say while all is well: {:?}", page.banners().await);
    });
}

#[test]
fn while_connecting_the_screen_says_so_and_the_led_is_orange() {
    // No offer: the stream never connects (the first 15 s).
    let cp = CloudPhone::start_with(json!({"options": {"offer": false}}));
    browser_test(&cp, Options::without_video(), |page| async move {
        page.wait_status("Connexion au flux…", Duration::from_secs(10)).await;
        page.wait_led(led::ORANGE, Duration::from_secs(5)).await;
        assert!(!page.status_is_closable("Connexion au flux…").await, "it covers the screen");
    });
}

#[test]
fn the_metrics_block_shows_a_round_trip_in_milliseconds() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::default(), |page| async move {
        let text = page
            .wait_js(
                "a ping in ms",
                Duration::from_secs(20),
                "const t = document.querySelector(arguments[0]).querySelectorAll('span')[0].innerText.trim(); return /^\\d+\\s*ms$/.test(t) ? t : null",
                vec![json!(browser::css_label(fr::INFO))],
            )
            .await;
        let ms = leading_number(text.as_str().unwrap()).unwrap();
        assert!(ms < 1000.0, "a plausible local round trip: {text}");
    });
}

#[test]
fn the_metrics_block_shows_the_frames_per_second_displayed() {
    // The fake sends 15 frames a second.
    let cp = CloudPhone::start();
    browser_test(&cp, Options::default(), |page| async move {
        let text = page
            .wait_js(
                "a frame rate above 5 fps",
                Duration::from_secs(20),
                "const t = document.querySelector(arguments[0]).querySelectorAll('span')[1].innerText.trim(); const m = /^(\\d+)\\s*fps$/.exec(t); return m && Number(m[1]) >= 5 ? t : null",
                vec![json!(browser::css_label(fr::INFO))],
            )
            .await;
        let fps = leading_number(text.as_str().unwrap()).unwrap();
        assert!(fps <= 20.0, "at most what the emulator sends: {text}");
    });
}

#[test]
fn the_reconnect_button_replaces_the_video_session_only() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        let p = phone.clone();
        blocking(move || p.wait_viewers("this page as the only viewer", Duration::from_secs(15), |n| n == 1));
        let sessions_before = phone.fake().record()["sessions"].as_array().unwrap().len();
        page.click_label(fr::RECONNECT).await;
        page.wait_js(
            "the video to play again after ↻",
            Duration::from_secs(45),
            "const v = document.querySelector('video'); const l = document.querySelector('[aria-label^=\"Connexion \"]'); \
             return !!v && v.videoWidth > 0 && !v.paused && !!l && l.getAttribute('aria-label') === 'Connexion connected' \
             && document.querySelector(arguments[0]).getAttribute('aria-busy') !== 'true'",
            vec![json!(browser::css_label(fr::RECONNECT))],
        )
        .await;
        let t0 = page.video().await["t"].as_f64().unwrap();
        page.sleep(Duration::from_secs(2)).await;
        assert!(page.video().await["t"].as_f64().unwrap() > t0 + 1.0, "the new session plays");
        let p = phone.clone();
        blocking(move || p.wait_viewers("one session again", Duration::from_secs(20), |n| n == 1));
        let record = phone.fake().record();
        let sessions = record["sessions"].as_array().unwrap();
        assert_eq!(sessions.len(), sessions_before + 1, "exactly one new WebRTC session: {sessions:?}");
        assert!(!sessions[sessions_before - 1]["closed"].is_null(), "the old session was ended: {sessions:?}");
        let events = record["events"].as_array().unwrap();
        assert!(events.is_empty(), "Android was not restarted: {events:?}");
    });
}

#[test]
fn rapid_reconnect_clicks_open_a_single_new_session() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        let p = phone.clone();
        blocking(move || p.wait_viewers("this page as the only viewer", Duration::from_secs(15), |n| n == 1));
        let before = phone.fake().record()["sessions"].as_array().unwrap().len();
        let button = page.by_label(fr::RECONNECT).await;
        for _ in 0..3 {
            let _ = button.click().await;
        }
        page.wait_for_video(Duration::from_secs(45)).await;
        page.sleep(Duration::from_secs(4)).await;
        let p = phone.clone();
        blocking(move || p.wait_viewers("one session once settled", Duration::from_secs(20), |n| n == 1));
        let after = phone.fake().record()["sessions"].as_array().unwrap().len();
        assert_eq!(after, before + 1, "three quick clicks open one new session, not three");
    });
}

#[test]
fn an_english_browser_gets_the_english_page() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options { wait_for_video: false, ..Options::english_browser() }, |page| async move {
        let labels = page.toolbar_labels().await;
        assert_eq!(
            labels,
            [en::POWER, en::VOLUME_DOWN, en::VOLUME_UP, en::INFO, en::RECENTS, en::HOME, en::BACK, en::OPTIONS, en::RECONNECT, en::FULLSCREEN]
        );
        assert_eq!(page.js("return document.documentElement.lang", vec![]).await, json!("en"));
    });
}

#[test]
fn the_page_holds_no_settings_until_one_is_changed() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        assert_eq!(page.stored_settings().await, serde_json::Value::Null, "a fresh browser stores nothing");
    });
}

#[test]
fn the_page_loads_without_errors_in_the_console() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::default(), |page| async move {
        // What the page reports through window.onerror and console.error
        // from now on, while it streams and polls for 5 s.
        page.js(
            "window.__errors = []; addEventListener('error', e => __errors.push(String(e.message))); \
             const original = console.error; console.error = (...a) => { __errors.push(a.map(String).join(' ')); original(...a); }; return true",
            vec![],
        )
        .await;
        page.sleep(Duration::from_secs(5)).await;
        let errors = page.js("return window.__errors", vec![]).await;
        assert_eq!(errors, json!([]), "no error while streaming");
    });
}

#[test]
fn the_video_is_muted_and_holds_each_track_once() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::default(), |page| async move {
        let video = page
            .js(
                "const v = document.querySelector('video'); const ids = v.srcObject ? v.srcObject.getTracks().map(t => t.id) : []; \
                 return {muted: v.muted, ids: ids, unique: new Set(ids).size, video: v.srcObject ? v.srcObject.getVideoTracks().length : 0}",
                vec![],
            )
            .await;
        assert_eq!(video["muted"], true, "the page plays no sound: {video}");
        assert_eq!(video["video"], 1, "one video track: {video}");
        assert_eq!(video["unique"], video["ids"].as_array().unwrap().len(), "no track twice: {video}");
    });
}

#[test]
fn the_page_says_connected_only_once_a_frame_arrives() {
    // The WebRTC session connects, but the emulator sends no picture yet.
    let cp = CloudPhone::start_with(json!({"options": {"frames": false}}));
    let phone = cp.clone();
    browser_test(&cp, Options::without_video(), |page| async move {
        let p = phone.clone();
        blocking(move || {
            let start = std::time::Instant::now();
            while !p.fake().state()["sessions"].as_array().unwrap().iter().any(|s| s["state"] == "connected") {
                assert!(start.elapsed() < Duration::from_secs(20), "the session never connected: {}", p.fake().state());
                std::thread::sleep(Duration::from_millis(200));
            }
        });
        page.sleep(Duration::from_secs(2)).await;
        assert_ne!(page.led().await["label"], "Connexion connected", "no frame, not connected");
        assert!(page.banners().await.iter().any(|b| b.contains("Connexion au flux…")), "{:?}", page.banners().await);
        phone.fake().control(json!({"frames": true}));
        page.wait_led(led::GREEN, Duration::from_secs(20)).await;
        assert_eq!(page.led().await["label"], "Connexion connected");
        page.wait_no_status("Connexion au flux…", Duration::from_secs(5)).await;
    });
}

#[test]
fn a_page_still_connecting_reopens_its_signalling_when_the_gateway_restarts() {
    // No offer: the page waits on its signalling socket, then the gateway
    // restarts and closes it.
    let cp = CloudPhone::start_with(json!({"options": {"offer": false}}));
    let phone = cp.clone();
    browser_test(&cp, Options::without_video(), |page| async move {
        page.wait_status("Connexion au flux…", SOON).await;
        let p = phone.clone();
        blocking(move || {
            p.wait_viewers("the page's signalling session", Duration::from_secs(10), |n| n == 1);
            let token = p.page_token();
            p.fake().action("restart_gateway");
            p.wait_new_token(&token, Duration::from_secs(20));
            wait_for("the page back on the new gateway, by itself", Duration::from_secs(30), || {
                let state = p.try_get_json("api/v1/state?viewer=e2e-count")?;
                (state["viewers"] == 1).then_some(())
            });
        });
    });
}

#[test]
fn after_a_long_outage_the_video_still_comes_back() {
    // Longer than the signalling driver's own retries (about 30 s).
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        phone.fake().action("stop_gateway");
        page.wait_status("Serveur injoignable", SOON).await;
        page.sleep(Duration::from_secs(45)).await;
        phone.fake().action("start_gateway");
        page.wait_no_status("Serveur injoignable", SOON).await;
        page.wait_js("the video playing again", Duration::from_secs(60),
            "const v = document.querySelector('video'); const l = document.querySelector('[aria-label^=\"Connexion \"]'); \
             return !!v && v.videoWidth > 0 && !v.paused && !!l && l.getAttribute('aria-label') === 'Connexion connected'", vec![]).await;
    });
}

#[test]
fn the_page_loads_while_androids_status_cannot_be_read() {
    // The emulator's gRPC is down before the page opens: GET
    // /api/v1/emulator/status fails, and the page still runs and says why.
    let cp = CloudPhone::start_with(json!({"options": {"offer": false}}));
    cp.fake().control(json!({"grpc": "down"}));
    browser_test(&cp, Options::without_video(), |page| async move {
        page.wait_status("Le serveur se reconnecte à Android…", SOON).await;
        assert_eq!(page.toolbar_labels().await.len(), 10, "the whole toolbar");
    });
}
