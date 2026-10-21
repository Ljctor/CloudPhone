//! The page when the browser blocks autoplay (Firefox's
//! `media.autoplay.default`): the picture never waits behind « Connexion
//! au flux… » for a gesture.
use cloudphone_e2e::browser::{browser_test, led, Options};
use cloudphone_e2e::*;
use std::time::Duration;

const SOON: Duration = Duration::from_secs(20);
const TAP_HINT: &str = "Touchez l’écran pour lancer la vidéo";

#[test]
fn the_picture_plays_without_a_gesture_when_audible_autoplay_is_blocked() {
    // 1: audible media blocked (Firefox's default). The stream carries an
    // audio track; the video still starts, muted, with no gesture.
    let cp = CloudPhone::start();
    browser_test(&cp, Options { autoplay: 1, ..Options::without_video() }, |page| async move {
        page.wait_for_video(SOON).await;
        page.wait_no_status("Connexion au flux…", Duration::from_secs(5)).await;
        page.wait_led(led::GREEN, Duration::from_secs(5)).await;
        let video = page.video().await;
        assert_eq!(video["paused"], false, "{video}");
        assert_eq!(page.js("return document.querySelector('video').muted", vec![]).await, true);
        page.sleep(Duration::from_secs(2)).await;
        let later = page.video().await;
        assert!(later["t"].as_f64().unwrap() > video["t"].as_f64().unwrap() + 1.0, "the picture moves: {video} -> {later}");
    });
}

#[test]
fn a_browser_blocking_all_autoplay_gets_a_tap_hint_then_the_picture() {
    // 5: all media blocked until a gesture. The page neither spins on
    // « Connexion au flux… » nor says connected over a frozen frame: it asks
    // for a tap, and a tap anywhere starts the video.
    let cp = CloudPhone::start();
    browser_test(&cp, Options { autoplay: 5, ..Options::without_video() }, |page| async move {
        page.wait_status(TAP_HINT, SOON).await;
        assert_ne!(page.led().await["label"], "Connexion connected", "a paused video is not connected");
        page.sleep(Duration::from_secs(25)).await;
        page.wait_status(TAP_HINT, Duration::from_secs(1)).await;
        let video = page.video().await;
        page.click_at(video["x"].as_f64().unwrap() + 50.0, video["y"].as_f64().unwrap() + 50.0).await;
        page.wait_for_video(SOON).await;
        page.wait_no_status(TAP_HINT, Duration::from_secs(5)).await;
        page.wait_no_status("Connexion au flux…", Duration::from_secs(1)).await;
        page.wait_led(led::GREEN, Duration::from_secs(5)).await;
    });
}
