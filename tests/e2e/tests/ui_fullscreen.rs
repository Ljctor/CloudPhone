//! Fullscreen and the fold button: tap folds the bar away behind a small
//! handle (drag to move, tap to unfold), long press docks the bar beside the
//! screen, and by default the bar folds 3 s after entering fullscreen.
use cloudphone_e2e::browser::{browser_test, css_label, fr, Options, Page};
use cloudphone_e2e::*;
use serde_json::json;
use std::time::{Duration, Instant};

const AUTOFOLD: &str = "Replier la barre 3 s après l’entrée en plein écran";

async fn enter_fullscreen(page: &Page) {
    page.click_label(fr::FULLSCREEN).await;
    page.wait_js("fullscreen", Duration::from_secs(5), "return !!document.fullscreenElement", vec![]).await;
}

async fn nav_shown(page: &Page) -> bool {
    let nav = page.rect("nav").await;
    nav["display"] != "none" && nav["w"].as_f64().unwrap_or(0.0) > 0.0
}

async fn set_autofold(page: &Page, on: bool) {
    page.open_options().await;
    let control = page.control(fr::OPTIONS_PANEL, AUTOFOLD).await;
    if page.control_state(&control).await["checked"] != json!(on) {
        control.click().await.unwrap();
    }
    page.click_label(fr::OPTIONS).await;
    page.wait_no_dialog().await;
}

/// Overlap, in CSS px, between the toolbar and the video.
async fn bar_video_overlap(page: &Page) -> f64 {
    let nav = page.rect("nav").await;
    let video = page.rect("video").await;
    let f = |v: &serde_json::Value, k: &str| v[k].as_f64().unwrap();
    let ox = (f(&nav, "x") + f(&nav, "w")).min(f(&video, "x") + f(&video, "w")) - f(&nav, "x").max(f(&video, "x"));
    let oy = (f(&nav, "y") + f(&nav, "h")).min(f(&video, "y") + f(&video, "h")) - f(&nav, "y").max(f(&video, "y"));
    if ox <= 0.0 || oy <= 0.0 { 0.0 } else { ox * oy }
}

#[test]
fn fullscreen_adds_the_fold_button_and_leaving_removes_it() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        set_autofold(&page, false).await;
        assert!(!page.has_label(fr::FOLD).await);
        enter_fullscreen(&page).await;
        page.wait_label_visible(fr::FOLD, true, Duration::from_secs(5)).await;
        assert_eq!(page.toolbar_labels().await.last().map(String::as_str), Some(fr::FOLD), "the fold button ends the toolbar");
        page.click_label(fr::FULLSCREEN).await;
        page.wait_js("leaving fullscreen", Duration::from_secs(5), "return !document.fullscreenElement", vec![]).await;
        page.wait_label_gone(fr::FOLD, Duration::from_secs(5)).await;
        set_autofold(&page, true).await;
    });
}

#[test]
fn by_default_the_bar_folds_about_3_s_after_entering_fullscreen() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        enter_fullscreen(&page).await;
        let entered = Instant::now();
        page.wait_label_visible(fr::FOLD, true, Duration::from_secs(2)).await;
        page.wait_for_label(fr::HANDLE, Duration::from_secs(8)).await;
        let folded_after = entered.elapsed();
        assert!(folded_after >= Duration::from_millis(2000), "not folded before ~3 s: {folded_after:?}");
        assert!(!nav_shown(&page).await, "the bar is away");
        assert!(page.label_visible(fr::HANDLE).await, "a handle is left to bring it back");
        // The screen takes the whole window.
        let section = page.rect(&css_label(fr::SCREEN)).await;
        let window = page.js("return [innerWidth, innerHeight]", vec![]).await;
        assert!((section["h"].as_f64().unwrap() - window[1].as_f64().unwrap()).abs() <= 2.0
            || (section["w"].as_f64().unwrap() - window[0].as_f64().unwrap()).abs() <= 2.0,
            "screen {section} fills the window {window} in one direction");
    });
}

#[test]
fn tapping_the_handle_unfolds_the_bar() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        enter_fullscreen(&page).await;
        page.wait_for_label(fr::HANDLE, Duration::from_secs(8)).await;
        page.click_label(fr::HANDLE).await;
        page.wait_label_gone(fr::HANDLE, Duration::from_secs(3)).await;
        assert!(nav_shown(&page).await, "the bar is back");
        assert!(page.label_visible(fr::FOLD).await);
        // Unfolding by hand does not fold again 3 s later.
        page.sleep(Duration::from_secs(4)).await;
        assert!(nav_shown(&page).await, "the bar stays after a manual unfold");
    });
}

#[test]
fn without_autofold_the_bar_stays_until_the_fold_button_is_tapped() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        set_autofold(&page, false).await;
        enter_fullscreen(&page).await;
        page.sleep(Duration::from_secs(5)).await;
        assert!(nav_shown(&page).await && !page.has_label(fr::HANDLE).await, "no automatic fold");
        page.click_label(fr::FOLD).await;
        page.wait_for_label(fr::HANDLE, Duration::from_secs(3)).await;
        assert!(!nav_shown(&page).await, "a tap folds the bar");
        page.click_label(fr::HANDLE).await;
        page.wait_label_gone(fr::HANDLE, Duration::from_secs(3)).await;
        set_autofold(&page, true).await;
    });
}

#[test]
fn the_handle_can_be_dragged_without_unfolding() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        enter_fullscreen(&page).await;
        let handle = page.wait_for_label(fr::HANDLE, Duration::from_secs(8)).await;
        let before = page.rect(&css_label(fr::HANDLE)).await;
        page.drag(&handle, -200.0, -250.0).await;
        page.sleep(Duration::from_millis(500)).await;
        assert!(page.has_label(fr::HANDLE).await && !nav_shown(&page).await, "a drag does not unfold the bar");
        let after = page.rect(&css_label(fr::HANDLE)).await;
        let dx = after["x"].as_f64().unwrap() - before["x"].as_f64().unwrap();
        let dy = after["y"].as_f64().unwrap() - before["y"].as_f64().unwrap();
        assert!(dx < -100.0 && dy < -100.0, "the handle followed the drag: {before} -> {after}");
        let window = page.js("return [innerWidth, innerHeight]", vec![]).await;
        assert!(after["x"].as_f64().unwrap() >= 0.0 && after["y"].as_f64().unwrap() >= 0.0
            && after["x"].as_f64().unwrap() + after["w"].as_f64().unwrap() <= window[0].as_f64().unwrap() + 1.0,
            "the handle stays in the window: {after} in {window}");
        page.click_label(fr::HANDLE).await;
        page.wait_label_gone(fr::HANDLE, Duration::from_secs(3)).await;
    });
}

#[test]
fn a_long_press_docks_the_bar_beside_the_screen_and_a_tap_floats_it_again() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        set_autofold(&page, false).await;
        enter_fullscreen(&page).await;
        let fold = page.wait_for_label(fr::FOLD, Duration::from_secs(5)).await;
        assert!(page.rect("nav").await["position"] == "fixed", "the bar floats over the screen in fullscreen");
        page.long_press(&fold, Duration::from_millis(1200)).await;
        let docked = page.wait_for_label(fr::DOCKED, Duration::from_secs(3)).await;
        assert_eq!(docked.attr("aria-pressed").await.unwrap().as_deref(), Some("true"));
        assert_ne!(page.rect("nav").await["position"], "fixed", "a docked bar keeps its own space");
        assert!(bar_video_overlap(&page).await < 1.0, "the docked bar does not cover the video");
        assert_eq!(page.stored_settings().await["barDocked"], true);
        page.sleep(Duration::from_secs(4)).await;
        assert!(page.has_label(fr::DOCKED).await && nav_shown(&page).await, "a docked bar stays");

        docked.click().await.unwrap();
        page.wait_for_label(fr::FOLD, Duration::from_secs(3)).await;
        assert_eq!(page.rect("nav").await["position"], "fixed", "floating again");
        assert_eq!(page.stored_settings().await["barDocked"], false);
        set_autofold(&page, true).await;
    });
}

#[test]
fn a_docked_bar_stays_docked_after_a_reload() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        set_autofold(&page, false).await;
        enter_fullscreen(&page).await;
        let fold = page.wait_for_label(fr::FOLD, Duration::from_secs(5)).await;
        page.long_press(&fold, Duration::from_millis(1200)).await;
        page.wait_for_label(fr::DOCKED, Duration::from_secs(3)).await;
        page.reload(false).await;
        enter_fullscreen(&page).await;
        let docked = page.wait_for_label(fr::DOCKED, Duration::from_secs(5)).await;
        docked.click().await.unwrap();
        page.wait_for_label(fr::FOLD, Duration::from_secs(3)).await;
        set_autofold(&page, true).await;
        assert_eq!(page.stored_settings().await["barDocked"], false, "defaults restored");
    });
}
