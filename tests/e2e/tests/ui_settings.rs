//! Client settings (the Options panel) are the gateway's (`GET`/`POST
//! /api/v1/settings`), the plugins' options too: they survive a reload, show
//! in another browser and survive a gateway restart. What earlier versions
//! kept in the browser (`localStorage`, key `cloudphone.settings`) moves to
//! the gateway once. Each test runs in a fresh Firefox profile and still
//! puts the defaults back before it ends.
use cloudphone_e2e::browser::{browser_test, en, fr, Options, Page};
use cloudphone_e2e::*;
use serde_json::{json, Value};
use std::time::Duration;

const MARKER: &str = "Afficher le curseur";
/// The test plugin's toggle (tests/fake-emulator/plugins/e2e-probe).
const PROBE_TOGGLE: &str = "Dessiner un cadre";
const PROBE: &str = "tests/fake-emulator/plugins/e2e-probe";
const AUTOFOLD: &str = "Replier la barre 3 s après l’entrée en plein écran";
const LANGUAGE: &str = "Langue";

async fn open_client_panel(page: &Page) {
    page.open_options().await;
}

/// Waits until the installed plugin's options are in the panel.
async fn wait_plugin_options(page: &Page) {
    page.wait_js("the plugin's options", Duration::from_secs(15),
        "const d = document.querySelector('[role=dialog]'); return !!d && d.innerText.includes(arguments[0])", vec![json!(PROBE_TOGGLE)]).await;
}

async fn checked(page: &Page, label: &str) -> bool {
    let panel = page.open_dialogs().await.pop().expect("an open panel");
    let control = page.control(&panel, label).await;
    page.control_state(&control).await["checked"].as_bool().unwrap()
}

async fn set_checked(page: &Page, label: &str, on: bool) {
    let panel = page.open_dialogs().await.pop().expect("an open panel");
    let control = page.control(&panel, label).await;
    if page.control_state(&control).await["checked"].as_bool().unwrap() != on {
        control.click().await.unwrap();
    }
    assert_eq!(checked(page, label).await, on, "{label:?} is now {on}");
}

async fn language(page: &Page) -> String {
    let panel = page.open_dialogs().await.pop().expect("an open panel");
    let label = if page.has_label(en::OPTIONS).await { "Language" } else { LANGUAGE };
    let control = page.control(&panel, label).await;
    page.control_state(&control).await["value"].as_str().unwrap().to_string()
}

async fn set_language(page: &Page, value: &str) {
    let panel = page.open_dialogs().await.pop().expect("an open panel");
    let label = if page.has_label(en::OPTIONS).await { "Language" } else { LANGUAGE };
    page.control(&panel, label).await.select_by_value(value).await.unwrap();
}

#[test]
fn the_defaults_are_the_documented_ones() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        open_client_panel(&page).await;
        assert!(checked(&page, MARKER).await, "touch marker on by default");
        assert!(checked(&page, AUTOFOLD).await, "fold 3 s after fullscreen on by default");
        assert_eq!(language(&page).await, "fr", "a French browser gets French");
        let options = page.control_state(&page.control(fr::OPTIONS_PANEL, LANGUAGE).await).await["options"].clone();
        assert_eq!(options, json!(["fr:Français", "en:English"]));
    });
}

#[test]
fn toggled_options_are_stored_and_survive_a_reload() {
    let cp = CloudPhone::start_with(json!({"plugins": [PROBE]}));
    browser_test(&cp, Options::without_video(), |page| async move {
        open_client_panel(&page).await;
        wait_plugin_options(&page).await;
        set_checked(&page, MARKER, false).await;
        set_checked(&page, PROBE_TOGGLE, true).await;
        set_checked(&page, AUTOFOLD, false).await;
        let stored = page.stored_settings().await;
        assert_eq!(stored["touchMarker"], false, "{stored}");
        assert_eq!(stored["plugins"]["e2e-probe"]["draw"], true, "a plugin's option is stored under its id: {stored}");
        assert_eq!(stored["autoFold"], false, "{stored}");

        page.reload(false).await;
        open_client_panel(&page).await;
        wait_plugin_options(&page).await;
        assert!(!checked(&page, MARKER).await, "marker stays off after reload");
        assert!(checked(&page, PROBE_TOGGLE).await, "the plugin option stays on after reload");
        assert!(!checked(&page, AUTOFOLD).await, "autofold stays off after reload");

        // Back to the defaults, and they survive a reload too.
        set_checked(&page, MARKER, true).await;
        set_checked(&page, PROBE_TOGGLE, false).await;
        set_checked(&page, AUTOFOLD, true).await;
        page.reload(false).await;
        open_client_panel(&page).await;
        wait_plugin_options(&page).await;
        assert!(checked(&page, MARKER).await && !checked(&page, PROBE_TOGGLE).await && checked(&page, AUTOFOLD).await);
        let stored = page.stored_settings().await;
        assert_eq!((stored["touchMarker"].clone(), stored["plugins"]["e2e-probe"]["draw"].clone(), stored["autoFold"].clone()), (json!(true), json!(false), json!(true)));
    });
}

#[test]
fn choosing_english_translates_the_page_and_survives_a_reload() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        open_client_panel(&page).await;
        set_language(&page, "en").await;
        page.wait_dialog(en::OPTIONS_PANEL).await;
        for label in [en::POWER, en::VOLUME_UP, en::INFO, en::HOME, en::BACK, en::OPTIONS, en::RECONNECT, en::FULLSCREEN] {
            page.wait_for_label(label, Duration::from_secs(5)).await;
        }
        let lines = page.dialog_lines(en::OPTIONS_PANEL).await;
        for heading in ["Options", "Language", "Show the cursor", "Fold the bar 3 s after entering fullscreen", "Plugins", "No plugin installed."] {
            assert!(lines.iter().any(|l| l == heading), "English {heading:?} in {lines:#?}");
        }
        assert_eq!(page.stored_settings().await["language"], "en");

        page.reload(false).await;
        assert!(page.has_label(en::POWER).await, "still English after reload: {:?}", page.toolbar_labels().await);
        assert_eq!(page.js("return document.documentElement.lang", vec![]).await, json!("en"));
        let panel = page.open_info(en::CLIENT_TAB).await;
        assert_eq!(panel, en::INFO_PANEL);
        let client = page.dialog_lines(en::INFO_PANEL).await;
        for heading in ["Information", "Client", "Server", "Network", "Display", "Input"] {
            assert!(client.iter().any(|l| l == heading), "English {heading:?} in {client:#?}");
        }
        page.open_info(en::SERVER_TAB).await;
        let server = page.dialog_lines(en::INFO_PANEL).await;
        for heading in ["Status", "Machine", "Android", "Stream sent", "Android settings", "Renderer", "Cores", "Device", "Resolution", "Apply"] {
            assert!(server.iter().any(|l| l == heading), "English section {heading:?} in {server:#?}");
        }

        // Back to French.
        page.open_options().await;
        set_language(&page, "fr").await;
        page.wait_dialog(fr::OPTIONS_PANEL).await;
        page.wait_for_label(fr::OPTIONS, Duration::from_secs(5)).await;
        page.reload(false).await;
        assert!(page.has_label(fr::POWER).await, "French again after reload");
        assert_eq!(page.stored_settings().await["language"], "fr");
    });
}

#[test]
fn an_english_browser_can_switch_the_page_to_french() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options { wait_for_video: false, ..Options::english_browser() }, |page| async move {
        open_client_panel(&page).await;
        assert_eq!(language(&page).await, "en");
        set_language(&page, "fr").await;
        page.wait_for_label(fr::POWER, Duration::from_secs(5)).await;
        page.reload(false).await;
        assert!(page.has_label(fr::POWER).await, "the choice beats the browser's language");
        open_client_panel(&page).await;
        set_language(&page, "en").await;
        page.wait_for_label(en::POWER, Duration::from_secs(5)).await;
    });
}

#[test]
fn an_option_set_in_one_browser_shows_in_another_and_after_a_gateway_restart() {
    let cp = CloudPhone::start_with(json!({"plugins": [PROBE]}));
    browser_test(&cp, Options::without_video(), |page| async move {
        open_client_panel(&page).await;
        wait_plugin_options(&page).await;
        set_checked(&page, MARKER, false).await;
        set_checked(&page, PROBE_TOGGLE, true).await;
        set_language(&page, "en").await;
        page.wait_for_label(en::POWER, Duration::from_secs(5)).await;
        let stored = page.stored_settings().await;
        assert_eq!((stored["touchMarker"].clone(), stored["language"].clone()), (json!(false), json!("en")), "{stored}");
        assert_eq!(page.browser_settings().await, Value::Null, "nothing kept in the browser");
    });
    let token = cp.page_token();
    cp.fake().action("restart_gateway");
    cp.wait_new_token(&token, Duration::from_secs(20));
    // A fresh Firefox profile: another device.
    browser_test(&cp, Options::without_video(), |page| async move {
        page.wait_for_label(en::POWER, Duration::from_secs(10)).await;
        page.open_options().await;
        page.wait_js("the plugin's options", Duration::from_secs(15),
            "const d = document.querySelector('[role=dialog]'); return !!d && d.innerText.includes(arguments[0])",
            vec![json!("Draw a frame")]).await;
        assert!(!checked(&page, "Show the cursor").await, "the cursor stays off");
        assert!(checked(&page, "Draw a frame").await, "the plugin's option stays on");
        assert_eq!(language(&page).await, "en");
        // Back to the defaults.
        set_checked(&page, "Show the cursor", true).await;
        set_checked(&page, "Draw a frame", false).await;
        set_language(&page, "fr").await;
        page.wait_for_label(fr::POWER, Duration::from_secs(5)).await;
    });
}

#[test]
fn settings_an_earlier_version_kept_in_the_browser_move_to_the_gateway_once() {
    let cp = CloudPhone::start_with(json!({"plugins": [PROBE]}));
    // The gateway already holds the cursor on: its value wins over the browser's.
    let set = cp.post_json("api/v1/settings", &json!({"touchMarker": true}));
    assert_eq!(set.status(), 200, "{:?}", set.text());
    browser_test(&cp, Options::without_video(), |page| async move {
        page.js("localStorage.setItem('cloudphone.settings', JSON.stringify({touchMarker: false, autoFold: false, \
                 plugins: {'e2e-probe': {draw: true}}}))", vec![]).await;
        page.reload(false).await;
        let stored = page.stored_settings().await;
        assert_eq!(stored["touchMarker"], true, "the gateway's value kept: {stored}");
        assert_eq!(stored["autoFold"], false, "the browser's value moved: {stored}");
        assert_eq!(stored["plugins"]["e2e-probe"]["draw"], true, "a plugin's option moved: {stored}");
        assert_eq!(page.browser_settings().await, Value::Null, "the browser's copy removed");
        open_client_panel(&page).await;
        wait_plugin_options(&page).await;
        assert!(checked(&page, MARKER).await && checked(&page, PROBE_TOGGLE).await && !checked(&page, AUTOFOLD).await);
        // A broken copy is only removed.
        page.js("localStorage.setItem('cloudphone.settings', '{not json')", vec![]).await;
        page.reload(false).await;
        assert!(page.has_label(fr::POWER).await, "the page still loads");
        assert_eq!(page.stored_settings().await["autoFold"], false);
        assert_eq!(page.browser_settings().await, Value::Null);
        open_client_panel(&page).await;
        wait_plugin_options(&page).await;
        set_checked(&page, PROBE_TOGGLE, false).await;
        set_checked(&page, AUTOFOLD, true).await;
    });
}
