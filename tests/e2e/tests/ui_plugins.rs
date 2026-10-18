//! Plugins in the page (Options → Plugins): each installed plugin's page
//! module is loaded, its options shown (toggle, number, action, status),
//! stored per plugin, and its drawing goes into its layer over the screen.
//! With the test plugins of tests/fake-emulator/plugins.
use cloudphone_e2e::browser::{blocking, browser_test, en, fr, Options, Page};
use cloudphone_e2e::*;
use fantoccini::Locator;
use serde_json::json;
use std::time::Duration;

const PROBE: &str = "tests/fake-emulator/plugins/e2e-probe";
const BROKEN: &str = "tests/fake-emulator/plugins/e2e-broken";
const O: &str = fr::OPTIONS_PANEL;

async fn open_plugins(page: &Page) {
    page.open_options().await;
    page.wait_js("the plugin's options", Duration::from_secs(15),
        "const d = document.querySelector('[role=dialog]'); return !!d && d.innerText.includes('Sonde e2e') && d.innerText.includes('Compteur')", vec![]).await;
}

fn probe_page() -> CloudPhone {
    CloudPhone::start_with(json!({"plugins": [PROBE]}))
}

async fn frame_drawn(page: &Page) -> serde_json::Value {
    page.js("const f = document.querySelector('[data-e2e-probe=frame]'); if (!f) return null; const r = f.getBoundingClientRect(); \
             return {w: r.width, colour: getComputedStyle(f).backgroundColor, inScreen: !!f.closest('section')}", vec![]).await
}

#[test]
fn without_plugins_the_options_say_none_is_installed() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        page.open_options().await;
        let lines = page.dialog_lines(O).await;
        let at = lines.iter().position(|l| l == "Plugins").unwrap_or_else(|| panic!("{lines:#?}"));
        assert_eq!(lines.get(at + 1).map(String::as_str), Some("Aucun plugin installé."));
    });
}

#[test]
fn a_plugin_shows_its_title_and_one_option_of_each_kind() {
    let cp = probe_page();
    browser_test(&cp, Options::default(), |page| async move {
        open_plugins(&page).await;
        let lines = page.dialog_lines(O).await;
        let at = lines.iter().position(|l| l == "Sonde e2e").unwrap_or_else(|| panic!("the plugin's title: {lines:#?}"));
        let rest = &lines[at..];
        for wanted in ["Dessiner un cadre", "Limite", "Compter", "Compteur", "Vidéo vue"] {
            assert!(rest.iter().any(|l| l == wanted), "{wanted:?} under the plugin: {lines:#?}");
        }
        assert!(!lines.iter().any(|l| l == "Aucun plugin installé."));
        let toggle = page.control_state(&page.control(O, "Dessiner un cadre").await).await;
        assert_eq!(toggle["checked"], false, "a toggle starts off: {toggle}");
        let number = page.control_state(&page.control(O, "Limite").await).await;
        assert_eq!(number["value"], "", "{number}");
        // The status rows read the plugin's state: its counter from its
        // gateway route, the video through the page's API.
        page.wait_dialog_value(O, "Compteur", Duration::from_secs(10), |v| v == "0").await;
        page.wait_dialog_value(O, "Vidéo vue", Duration::from_secs(10), |v| v == "480×1040").await;
    });
}

#[test]
fn a_plugin_toggle_draws_in_its_layer_and_is_remembered() {
    let cp = probe_page();
    browser_test(&cp, Options::default(), |page| async move {
        open_plugins(&page).await;
        assert!(frame_drawn(&page).await.is_null());
        page.control(O, "Dessiner un cadre").await.click().await.unwrap();
        let frame = page.wait_js("the plugin's frame", Duration::from_secs(5),
            "return document.querySelector('[data-e2e-probe=frame]') ? true : null", vec![]).await;
        assert_eq!(frame, json!(true));
        let frame = frame_drawn(&page).await;
        assert_eq!(frame["colour"], "rgb(255, 0, 255)", "the colour from its helper module: {frame}");
        assert_eq!(frame["inScreen"], true, "drawn over the screen: {frame}");
        let surface = page.rect(&cloudphone_e2e::browser::css_label(fr::TOUCH_SURFACE)).await;
        assert!((frame["w"].as_f64().unwrap() - surface["w"].as_f64().unwrap()).abs() < 2.0, "screenWidth() is the shown screen's: {frame} vs {surface}");
        // The layer lets touches through to Android.
        let events = page.js("const l = document.querySelector('[data-e2e-probe=frame]').parentElement; return getComputedStyle(l).pointerEvents", vec![]).await;
        assert_eq!(events, "none");
        assert_eq!(page.stored_settings().await["plugins"]["e2e-probe"]["draw"], true);
        page.reload(true).await;
        page.wait_js("the frame after reload", Duration::from_secs(15), "return !!document.querySelector('[data-e2e-probe=frame]')", vec![]).await;
        open_plugins(&page).await;
        page.control(O, "Dessiner un cadre").await.click().await.unwrap();
        page.wait_js("the frame to go", Duration::from_secs(5), "return !document.querySelector('[data-e2e-probe=frame]')", vec![]).await;
        assert_eq!(page.stored_settings().await["plugins"]["e2e-probe"]["draw"], false);
    });
}

#[test]
fn a_plugin_number_field_keeps_digits_only_and_is_stored_as_text() {
    let cp = probe_page();
    browser_test(&cp, Options::without_video(), |page| async move {
        open_plugins(&page).await;
        let field = page.control(O, "Limite").await;
        field.send_keys("12ab3").await.unwrap();
        let state = page.control_state(&page.control(O, "Limite").await).await;
        assert_eq!(state["value"], "123", "{state}");
        assert_eq!(page.stored_settings().await["plugins"]["e2e-probe"]["limit"], "123");
        page.reload(false).await;
        open_plugins(&page).await;
        assert_eq!(page.control_state(&page.control(O, "Limite").await).await["value"], "123", "kept after reload");
    });
}

#[test]
fn a_plugin_action_posts_with_the_page_token() {
    let cp = probe_page();
    let phone = cp.clone();
    browser_test(&cp, Options::without_video(), |page| async move {
        open_plugins(&page).await;
        page.wait_dialog_value(O, "Compteur", Duration::from_secs(10), |v| v == "0").await;
        let button = page.client.find(Locator::XPath("//div[@role='dialog']//button[normalize-space()='Compter']")).await.unwrap();
        button.click().await.unwrap();
        page.wait_dialog_value(O, "Compteur", Duration::from_secs(10), |v| v == "1").await;
        button.click().await.unwrap();
        page.wait_dialog_value(O, "Compteur", Duration::from_secs(10), |v| v == "2").await;
        let p = phone.clone();
        assert_eq!(blocking(move || p.get_json("api/v1/plugins/e2e-probe/count"))["count"], 2, "the gateway counted both");
    });
}

#[test]
fn a_plugin_that_fails_to_start_is_reported_and_the_others_still_work() {
    let cp = CloudPhone::start_with(json!({"plugins": [PROBE, BROKEN]}));
    browser_test(&cp, Options::default(), |page| async move {
        open_plugins(&page).await;
        let text = page.dialog_text(O).await;
        assert!(text.contains("Greffon cassé"), "the broken plugin is named: {text}");
        assert!(text.contains("Échec : e2e-broken refuses to start"), "with its error: {text}");
        assert!(page.banners().await.is_empty(), "no banner for it: {:?}", page.banners().await);
        page.wait_for_video(Duration::from_secs(20)).await;
    });
}

#[test]
fn plugin_texts_follow_the_page_language() {
    let cp = probe_page();
    browser_test(&cp, Options { wait_for_video: false, ..Options::english_browser() }, |page| async move {
        page.open_options().await;
        page.wait_js("the plugin's English options", Duration::from_secs(15),
            "const d = document.querySelector('[role=dialog]'); return !!d && d.innerText.includes('Draw a frame')", vec![]).await;
        let lines = page.dialog_lines(en::OPTIONS_PANEL).await;
        for wanted in ["Draw a frame", "Limit", "Count", "Counter", "Video seen"] {
            assert!(lines.iter().any(|l| l == wanted), "{wanted:?}: {lines:#?}");
        }
    });
}
