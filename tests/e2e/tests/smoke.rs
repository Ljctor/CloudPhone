//! Smoke and critical user journeys on a deployed instance: the real
//! emulator, the real Android, the real network path. Built only with the
//! `smoke` feature and run against CLOUDPHONE_URL:
//!
//!     CLOUDPHONE_URL=http://<server>:8000/ cargo test --features smoke --test smoke -- --test-threads=1
//!
//! They act on the phone: one volume step up then down, the notification
//! shade opened then closed with Back. Nothing else (no size or settings
//! change, no restart). Run them when nobody is using the phone.
use cloudphone_e2e::browser::{browser_test, fr, Frame, Options, Page};
use cloudphone_e2e::*;
use std::time::{Duration, Instant};

/// Right edge, middle: where Android draws its volume panel in portrait.
const VOLUME_AREA: (f64, f64, f64, f64) = (0.6, 0.1, 1.0, 0.8);
/// Upper half: where the notification shade comes down.
const SHADE_AREA: (f64, f64, f64, f64) = (0.0, 0.0, 1.0, 0.5);
const COLS: u32 = 96;
const THRESHOLD: u8 = 40;

/// The largest change between frames taken over `duration` in `area`, for
/// the noise of an unchanged screen (animations, clock).
async fn noise(page: &Page, base: &Frame, area: (f64, f64, f64, f64), duration: Duration) -> f64 {
    let start = Instant::now();
    let mut worst: f64 = 0.0;
    while start.elapsed() < duration {
        page.sleep(Duration::from_millis(300)).await;
        worst = worst.max(page.frame(COLS).await.changed(base, area, THRESHOLD));
    }
    worst
}

/// Waits until the area differs from `base` by more than `share`; gives the largest share seen.
async fn wait_change(page: &Page, base: &Frame, area: (f64, f64, f64, f64), share: f64, timeout: Duration) -> f64 {
    let start = Instant::now();
    let mut best: f64 = 0.0;
    while start.elapsed() < timeout {
        best = best.max(page.frame(COLS).await.changed(base, area, THRESHOLD));
        if best > share {
            return best;
        }
        page.sleep(Duration::from_millis(150)).await;
    }
    best
}

/// Waits until the area is back within `share` of `base`; gives the last share.
async fn wait_back(page: &Page, base: &Frame, area: (f64, f64, f64, f64), share: f64, timeout: Duration) -> f64 {
    let start = Instant::now();
    loop {
        let now = page.frame(COLS).await.changed(base, area, THRESHOLD);
        if now <= share || start.elapsed() > timeout {
            return now;
        }
        page.sleep(Duration::from_millis(300)).await;
    }
}

#[test]
fn the_page_is_served_with_its_token_and_android_is_up() {
    let cp = CloudPhone::remote();
    let token = cp.page_token();
    assert!(token.len() >= 16, "a page token");
    assert_eq!(cp.get_json("api/v1/ping")["status"], "ok");
    let state = cp.get_json("api/v1/state");
    assert_eq!(state["emulator"]["active"], "active", "{state}");
    assert_eq!(state["android"]["booted"], true, "{state}");
}

#[test]
fn the_video_plays_in_a_browser() {
    let cp = CloudPhone::remote();
    browser_test(&cp, Options::default(), |page| async move {
        let first = page.video().await;
        page.sleep(Duration::from_secs(3)).await;
        let later = page.video().await;
        assert!(later["t"].as_f64().unwrap() > first["t"].as_f64().unwrap(), "the video advances: {first} → {later}");
        assert!(page.banners().await.is_empty() || page.banners().await.iter().all(|b| b.contains("regarde") || b.contains("chargé")), "no problem shown: {:?}", page.banners().await);
    });
}

#[test]
fn volume_up_shows_androids_volume_panel_in_the_video() {
    let cp = CloudPhone::remote();
    browser_test(&cp, Options::default(), |page| async move {
        page.sleep(Duration::from_secs(2)).await;
        let base = page.frame(COLS).await;
        let quiet = noise(&page, &base, VOLUME_AREA, Duration::from_secs(3)).await;
        page.click_label(fr::VOLUME_UP).await;
        let shown = wait_change(&page, &base, VOLUME_AREA, quiet + 0.04, Duration::from_secs(5)).await;
        // Put the level back (this shows the panel again, briefly).
        page.click_label(fr::VOLUME_DOWN).await;
        assert!(shown > quiet + 0.04, "the volume panel appears on the right: {shown:.3} changed vs {quiet:.3} noise");
        let gone = wait_back(&page, &base, VOLUME_AREA, quiet + 0.02, Duration::from_secs(15)).await;
        assert!(gone <= quiet + 0.02, "the panel goes away by itself: still {gone:.3} changed (noise {quiet:.3})");
    });
}

#[test]
fn a_swipe_from_the_top_opens_the_notification_shade_and_back_closes_it() {
    let cp = CloudPhone::remote();
    browser_test(&cp, Options::default(), |page| async move {
        page.sleep(Duration::from_secs(2)).await;
        let base = page.frame(COLS).await;
        let quiet = noise(&page, &base, SHADE_AREA, Duration::from_secs(3)).await;
        let video = page.video().await;
        let (x, y, w, h) = (video["x"].as_f64().unwrap(), video["y"].as_f64().unwrap(), video["cssW"].as_f64().unwrap(), video["cssH"].as_f64().unwrap());
        let from = (x + w / 2.0, y + 2.0);
        let to = (x + w / 2.0, y + h * 0.6);
        let mut opened = 0.0;
        // A fullscreen app first shows the system bars; a second swipe opens the shade.
        for _ in 0..2 {
            page.swipe(from, to, Duration::from_millis(400)).await;
            opened = wait_change(&page, &base, SHADE_AREA, quiet + 0.25, Duration::from_secs(4)).await;
            if opened > quiet + 0.25 {
                break;
            }
        }
        assert!(opened > quiet + 0.25, "the shade covers the upper half: {opened:.3} changed vs {quiet:.3} noise");
        page.sleep(Duration::from_millis(500)).await;
        page.click_label(fr::BACK).await;
        let closed = wait_back(&page, &base, SHADE_AREA, quiet + 0.05, Duration::from_secs(8)).await;
        assert!(closed <= quiet + 0.05, "Back closes the shade: still {closed:.3} changed (noise {quiet:.3})");
        // The page says which path the touches took.
        page.open_info(fr::CLIENT_TAB).await;
        let path = page.dialog_value(fr::INFO_PANEL, "Touches via").await.unwrap_or_default();
        assert_eq!(path, "data channel", "touches go over the emulator's data channel");
    });
}
