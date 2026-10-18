//! Logs in the page: records with notify become toasts over the screen
//! (coloured by level, closable, normal ones going by themselves, errors
//! staying, the same event once), and the Information panel lists the
//! server's and the page's records with a level filter.
use cloudphone_e2e::browser::{blocking, browser_test, fr, Options, Page};
use cloudphone_e2e::*;
use serde_json::{json, Value};
use std::time::Duration;

const SOON: Duration = Duration::from_secs(20);
const WHITE: &str = "rgb(255, 255, 255)";
const RED: &str = "rgb(255, 69, 58)";

/// The toasts shown: [{level, text, colour}].
async fn toasts(page: &Page) -> Vec<Value> {
    page.js("return [...document.querySelectorAll('[data-toast]')].map(t => ({level: t.dataset.toast, \
             text: t.innerText.trim(), colour: getComputedStyle(t.querySelector('span')).color}))", vec![])
        .await
        .as_array()
        .cloned()
        .unwrap_or_default()
}

async fn wait_toast(page: &Page, text: &str) -> Value {
    page.wait_js(&format!("a toast saying {text:?}"), SOON,
        "const t = [...document.querySelectorAll('[data-toast]')].find(t => t.innerText.includes(arguments[0])); \
         return t ? {level: t.dataset.toast, text: t.innerText.trim(), colour: getComputedStyle(t.querySelector('span')).color} : null",
        vec![json!(text)]).await
}

async fn close_toast(page: &Page, text: &str) {
    page.js("const t = [...document.querySelectorAll('[data-toast]')].find(t => t.innerText.includes(arguments[0])); \
             t.querySelector('button').click()", vec![json!(text)]).await;
}

#[test]
fn a_notify_record_is_a_toast_over_the_screen_that_goes_by_itself() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        // Another device connects: a normal record with notify.
        let other = phone.clone();
        let viewer = blocking(move || Viewer::open(&other, &viewer_id("toast")));
        let toast = wait_toast(&page, "Un autre appareil s’est connecté").await;
        assert_eq!(toast["level"], "normal");
        assert_eq!(toast["colour"], WHITE, "normal records in the theme's foreground: {toast}");
        // Over the screen, not over the toolbar.
        let stack = page.rect("[aria-label=\"Notifications\"]").await;
        let screen = page.rect("[aria-label=\"Écran Android\"]").await;
        let bar = page.rect("nav").await;
        let bottom = stack["y"].as_f64().unwrap() + stack["h"].as_f64().unwrap();
        assert!(bottom <= screen["y"].as_f64().unwrap() + screen["h"].as_f64().unwrap() + 0.5, "{stack} in {screen}");
        assert!(bottom <= bar["y"].as_f64().unwrap() || stack["x"].as_f64().unwrap() + stack["w"].as_f64().unwrap() <= bar["x"].as_f64().unwrap() + 0.5,
            "not over the toolbar: {stack} {bar}");
        page.wait_js("the normal toast to go by itself", Duration::from_secs(12),
            "return ![...document.querySelectorAll('[data-toast]')].some(t => t.innerText.includes('Un autre appareil s’est connecté'))", vec![]).await;
        blocking(move || viewer.close());
    });
}

#[test]
fn an_error_toast_stays_once_until_closed() {
    let cp = CloudPhone::start_with(json!({"options": {"adb_fails": true}}));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        // Give the page its first read of the log: toasts are for what comes after.
        page.sleep(Duration::from_secs(5)).await;
        let other = phone.clone();
        blocking(move || {
            for _ in 0..2 {
                assert_eq!(other.post_json("api/v1/emulator/key", &json!({"key": "GoHome"})).status(), 500);
            }
        });
        let toast = wait_toast(&page, "adb ne joint plus Android").await;
        assert_eq!(toast["level"], "error");
        assert_eq!(toast["colour"], RED, "{toast}");
        page.sleep(Duration::from_secs(10)).await;
        let shown: Vec<Value> = toasts(&page).await.into_iter().filter(|t| t["text"].as_str().unwrap().contains("adb ne joint plus")).collect();
        assert_eq!(shown.len(), 1, "an error stays, once: {shown:?}");
        close_toast(&page, "adb ne joint plus Android").await;
        page.wait_js("the toast closed", Duration::from_secs(5),
            "return ![...document.querySelectorAll('[data-toast]')].some(t => t.innerText.includes('adb ne joint plus'))", vec![]).await;
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
