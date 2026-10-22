//! Logs in the page: alerts reach the user only through ntfy (phone
//! alerts), so a record with notify never pops up over the screen (no
//! toast, no system notification), while its phone alert is still sent;
//! the Information panel lists the server's and the page's records with a
//! level filter.
use cloudphone_e2e::browser::{blocking, browser_test, fr, Options, Page};
use cloudphone_e2e::*;
use serde_json::{json, Value};
use std::time::Duration;

const SOON: Duration = Duration::from_secs(20);
const WHITE: &str = "rgb(255, 255, 255)";
const ORANGE: &str = "rgb(255, 159, 10)";
const RED: &str = "rgb(255, 69, 58)";
const PROBE: &str = "tests/fake-emulator/plugins/e2e-probe";

/// Counts the system notifications the page would raise, as if the tab
/// were hidden and the browser allowed them (the old toasts' fallback).
async fn watch_system_notifications(page: &Page) {
    page.js("window.__e2eNotes = []; \
             window.Notification = class { constructor(title, options) { window.__e2eNotes.push(options?.body ?? title); } \
               static get permission() { return 'granted'; } static requestPermission() { return Promise.resolve('granted'); } }; \
             Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' })", vec![]).await;
}

/// Asserts that nothing over the screen says any of `texts` for `duration`
/// (longer than the page's 4 s log poll): no toast, no notification stack,
/// no text over the Android screen, no system notification.
async fn never_pops_up(page: &Page, texts: &[&str], duration: Duration) {
    let start = std::time::Instant::now();
    while start.elapsed() < duration {
        let seen = page.js("const s = document.querySelector('[aria-label=\"Écran Android\"]'); \
             return {stack: document.querySelectorAll('[data-toast], [aria-label=\"Notifications\"], [aria-label=\"Notifications\"] *').length, \
                     dialogs: document.querySelectorAll('[role=dialog], [role=alertdialog], [role=alert]').length, \
                     screen: s ? s.innerText : '', notes: window.__e2eNotes ?? []}", vec![]).await;
        assert_eq!(seen["stack"], 0, "no toast: {seen}");
        assert_eq!(seen["dialogs"], 0, "no popup or dialog: {seen}");
        assert_eq!(seen["notes"], json!([]), "no system notification: {seen}");
        let screen = seen["screen"].as_str().unwrap_or_default();
        for text in texts {
            assert!(!screen.contains(text), "{text:?} shown over the screen: {screen:?}");
        }
        page.sleep(Duration::from_millis(250)).await;
    }
}

/// The records of one log of the Information panel (`tab`, its section
/// `title`), unfolded: [{level, text, colour}], once one contains `text`.
async fn logged(page: &Page, tab: &str, title: &str, text: &str) -> Vec<Value> {
    page.open_info(tab).await;
    page.js("const s = [...document.querySelectorAll('[role=dialog] summary')].find(s => s.innerText.includes(arguments[0])); \
             if (s && !s.parentElement.open) s.click()", vec![json!(title)]).await;
    let rows = page.wait_js(&format!("{text:?} in {title:?}"), SOON,
        "const r = [...document.querySelectorAll('[role=dialog] [data-level]')].map(e => ({level: e.dataset.level, \
           text: e.lastElementChild.innerText.trim(), colour: getComputedStyle(e.lastElementChild).color})); \
         return r.some(e => e.text.includes(arguments[0])) ? r : null", vec![json!(text)]).await;
    rows.as_array().cloned().unwrap_or_default()
}

fn find<'a>(rows: &'a [Value], text: &str) -> &'a Value {
    rows.iter().find(|r| r["text"].as_str().unwrap_or_default().contains(text)).unwrap_or_else(|| panic!("{text:?} in {rows:#?}"))
}

#[test]
fn a_notify_record_never_pops_up_and_its_phone_alert_is_still_sent() {
    let cp = CloudPhone::start_with(json!({"plugins": [PROBE]}));
    assert_eq!(cp.post_json("api/v1/notify", &json!({"enabled": true})).status(), 200);
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        watch_system_notifications(&page).await;
        // Give the page its first read of the log: the toasts were for what came after.
        page.sleep(Duration::from_secs(5)).await;
        // Another device connects (a normal record with notify), and the
        // plugin alerts (a warning with notify, and its phone alert).
        let other = phone.clone();
        let viewer = blocking(move || Viewer::open(&other, &viewer_id("no-toast")));
        let other = phone.clone();
        blocking(move || {
            let answer = other.post_json("api/v1/plugins/e2e-probe/alert", &json!({"text": "Probe alert: the game stalled"}));
            assert_eq!(answer.status(), 200);
            assert_eq!(answer.json().unwrap()["sent"], true, "the phone alert went out");
        });
        let other = phone.clone();
        let posts = blocking(move || wait_for("the ntfy post", SOON, || {
            let posts = other.fake().ntfy_posts();
            posts.iter().any(|p| p["text"] == "Probe alert: the game stalled").then_some(posts)
        }));
        assert_eq!(posts.iter().filter(|p| p["text"] == "Probe alert: the game stalled").count(), 1, "one phone alert: {posts:?}");
        never_pops_up(&page, &["Another device connected", "Probe alert"], Duration::from_secs(9)).await;
        // Both are still in the server's log, coloured by level.
        let rows = logged(&page, fr::SERVER_TAB, "Journaux du serveur", "Probe alert: the game stalled").await;
        assert_eq!(find(&rows, "Probe alert: the game stalled")["colour"], ORANGE, "{rows:#?}");
        assert_eq!(find(&rows, "Another device connected")["colour"], WHITE, "{rows:#?}");
        blocking(move || viewer.close());
    });
}

#[test]
fn an_error_record_never_pops_up_and_stays_in_the_server_log() {
    let cp = CloudPhone::start_with(json!({"options": {"adb_fails": true}}));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        watch_system_notifications(&page).await;
        page.sleep(Duration::from_secs(5)).await;
        let other = phone.clone();
        blocking(move || {
            for _ in 0..2 {
                assert_eq!(other.post_json("api/v1/emulator/key", &json!({"key": "GoHome"})).status(), 500);
            }
        });
        never_pops_up(&page, &["adb no longer reaches Android"], Duration::from_secs(9)).await;
        let rows = logged(&page, fr::SERVER_TAB, "Journaux du serveur", "adb no longer reaches Android").await;
        let record = find(&rows, "adb no longer reaches Android");
        assert_eq!((record["level"].as_str(), record["colour"].as_str()), (Some("error"), Some(RED)), "{record}");
        let shown = rows.iter().filter(|r| r["text"].as_str().unwrap().contains("adb no longer reaches")).count();
        assert_eq!(shown, 1, "once: {rows:#?}");
    });
}

#[test]
fn a_plugins_page_warning_is_a_client_log_record_that_never_pops_up() {
    let cp = CloudPhone::start_with(json!({"plugins": [PROBE]}));
    browser_test(&cp, Options::default(), |page| async move {
        watch_system_notifications(&page).await;
        page.open_options().await;
        page.wait_js("the plugin's options", Duration::from_secs(15),
            "const d = document.querySelector('[role=dialog]'); return !!d && d.innerText.includes('Avertir')", vec![]).await;
        page.js("[...document.querySelectorAll('[role=dialog] button')].find(b => b.innerText.trim() === 'Avertir').click()", vec![]).await;
        page.click_label(fr::OPTIONS).await;
        page.wait_js("the options closed", Duration::from_secs(5), "return !document.querySelector('[role=dialog]')", vec![]).await;
        never_pops_up(&page, &["Probe warning"], Duration::from_secs(3)).await;
        let rows = logged(&page, fr::CLIENT_TAB, "Journaux du client", "Sonde e2e: Probe warning").await;
        let record = find(&rows, "Sonde e2e: Probe warning");
        assert_eq!((record["level"].as_str(), record["colour"].as_str()), (Some("warning"), Some(ORANGE)), "{record}");
    });
}

#[test]
fn the_server_log_lists_records_coloured_by_level_with_a_filter() {
    let cp = CloudPhone::start();
    // A warning (refused request) and an error (failed request) on the server.
    assert_eq!(cp.post_json("api/v1/display", &json!({"width": 361, "height": 780, "density": 160})).status(), 400);
    cp.fake().control(json!({"fail_next": {"display": "boom"}}));
    assert_eq!(cp.post_json("api/v1/display", &json!({"width": 360, "height": 780, "density": 160})).status(), 202);
    wait_for("the failed change", SOON, || {
        let logs = cp.try_get_json("api/v1/logs")?;
        logs["records"].as_array()?.iter().any(|r| r["level"] == "error").then_some(())
    });
    browser_test(&cp, Options::default(), |page| async move {
        page.open_info(fr::SERVER_TAB).await;
        page.js("const s = [...document.querySelectorAll('[role=dialog] summary')].find(s => s.innerText.includes('Journaux du serveur')); \
                 s.click()", vec![]).await;
        let levels = page.wait_js("the server's records", SOON,
            "const r = [...document.querySelectorAll('[role=dialog] [data-level]')]; \
             return r.length >= 3 ? r.map(e => [e.dataset.level, getComputedStyle(e.lastElementChild).color]) : null", vec![]).await;
        let pairs: Vec<(String, String)> = levels.as_array().unwrap().iter()
            .map(|p| (p[0].as_str().unwrap().to_string(), p[1].as_str().unwrap().to_string())).collect();
        for (level, colour) in &pairs {
            let expected = match level.as_str() { "normal" => WHITE, "warning" => "rgb(255, 159, 10)", "error" => RED, other => panic!("level {other}") };
            assert_eq!(colour, expected, "{level}");
        }
        assert!(pairs.iter().any(|(l, _)| l == "warning") && pairs.iter().any(|(l, _)| l == "error"), "{pairs:?}");
        // Errors only.
        page.control(fr::INFO_PANEL, "Niveau").await.select_by_value("errors").await.unwrap();
        let only = page.wait_js("errors only", SOON,
            "const r = [...document.querySelectorAll('[role=dialog] [data-level]')].map(e => e.dataset.level); \
             return r.length && r.every(l => l === 'error') ? r : null", vec![]).await;
        assert!(!only.as_array().unwrap().is_empty());
        let text = page.dialog_text(fr::INFO_PANEL).await;
        assert!(text.contains("journalctl -u cloudphone-display"), "the error says what to do: {text}");
    });
}
