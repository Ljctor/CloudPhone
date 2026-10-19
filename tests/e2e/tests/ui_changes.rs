//! Changes that restart Android, made from the page: the server tab's form
//! ("Réglages d’Android": renderer, cores, memory, device shape and
//! resolution) sends one request, the page follows it (pending, applying,
//! failed) and, when the screen size changed, reloads at the new size. The
//! fake answers the requests the way the root services do; nothing touches a
//! real phone.
//!
//! The fake starts at 2 cores: the page keeps the running core count in its
//! request, and the gateway refuses more cores than the host's threads.
use cloudphone_e2e::browser::{blocking, browser_test, fr, Options, Page};
use cloudphone_e2e::*;
use fantoccini::Locator;
use serde_json::{json, Value};
use std::time::Duration;

const P: &str = fr::INFO_PANEL;
const APPLY: &str = "//div[@role='dialog']//button[normalize-space()='Appliquer']";

async fn open_form(page: &Page) {
    page.open_info(fr::SERVER_TAB).await;
    page.wait_js(
        "the Android settings form",
        Duration::from_secs(15),
        "const d = document.querySelector('[role=dialog]'); return d && d.querySelectorAll('select').length >= 5",
        vec![],
    )
    .await;
}

/// Answers the page's confirmation with `answer` and keeps its message.
async fn answer_confirm(page: &Page, answer: bool) {
    page.js("window.__confirmed = []; window.confirm = (m) => { window.__confirmed.push(m); return arguments[0]; }".replace("arguments[0]", if answer { "true" } else { "false" }).as_str(), vec![]).await;
}

async fn confirmations(page: &Page) -> Vec<String> {
    browser::strings(&page.js("return window.__confirmed || []", vec![]).await)
}

use cloudphone_e2e::browser;

async fn select(page: &Page, label: &str, value: &str) {
    page.control(P, label).await.select_by_value(value).await.unwrap_or_else(|e| panic!("{label} = {value}: {e}"));
}

async fn click_apply(page: &Page) {
    let button = page.client.find(Locator::XPath(APPLY)).await.expect("the Apply button");
    assert_eq!(button.prop("disabled").await.unwrap().as_deref(), Some("false"), "Apply is enabled");
    button.click().await.unwrap();
}

async fn apply_disabled(page: &Page) -> bool {
    let button = page.client.find(Locator::XPath(APPLY)).await.expect("the Apply button");
    button.prop("disabled").await.unwrap().as_deref() == Some("true")
}

/// The settings requests the root service received (request lines).
fn settings_requests(phone: &CloudPhone) -> Vec<Value> {
    let record = phone.fake().record();
    record["requests"]["settings"].as_array().into_iter().flatten().filter(|e| e.get("request").is_some()).cloned().collect()
}

/// Marks this page load; [`reloaded`] tells whether the page loaded again.
async fn mark_load(page: &Page) {
    page.js("window.__e2eLoad = true", vec![]).await;
}

async fn wait_reload(page: &Page, timeout: Duration) {
    page.wait_js("the page to reload", timeout, "return document.readyState === 'complete' && !window.__e2eLoad", vec![]).await;
}

#[test]
fn a_new_resolution_is_one_request_and_the_page_reloads_at_the_new_size() {
    // Applying for 3 s: longer than a state poll plus the gateway's state
    // cache (2 s each), so the page always sees it.
    let cp = CloudPhone::start_with(json!({"settings": {"cores": 2}, "options": {"apply_seconds": 3}}));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        open_form(&page).await;
        mark_load(&page).await;
        select(&page, "Résolution", "720").await;
        answer_confirm(&page, true).await;
        click_apply(&page).await;
        let asked = confirmations(&page).await;
        assert_eq!(asked.len(), 1, "one confirmation: {asked:?}");
        assert!(asked[0].contains("Android va redémarrer"), "{asked:?}");
        // While it applies, the screen is covered.
        page.wait_status("Changement des réglages d’Android", Duration::from_secs(10)).await;
        // One request, with the size and the unchanged settings together.
        let p = phone.clone();
        let requests = blocking(move || {
            p.fake().wait_record("the settings request", Duration::from_secs(10), |r| {
                let asked: Vec<Value> = r["requests"]["settings"].as_array()?.iter().filter(|e| e.get("request").is_some()).cloned().collect();
                (!asked.is_empty()).then_some(asked)
            })
        });
        assert_eq!(requests.len(), 1, "one request: {requests:?}");
        let request = &requests[0];
        assert_eq!(request["request"], "lavapipe 2 4096 720 1560 320", "renderer cores memory width height density: {request}");
        assert!(phone.fake().record()["requests"]["display"].as_array().unwrap().is_empty(), "no separate display request");
        // Android restarts at 720×1560, the gateway with it, and the page
        // reloads: video, touch surface and touches follow the new size.
        wait_reload(&page, Duration::from_secs(60)).await;
        page.wait_for_video(Duration::from_secs(45)).await;
        page.wait_js("the 720×1560 stream", Duration::from_secs(30),
            "const v = document.querySelector('video'); return !!v && v.videoWidth === 720 && v.videoHeight === 1560", vec![]).await;
        page.wait_no_status("Changement des réglages", Duration::from_secs(10)).await;
        let display = phone.get_json("api/v1/display");
        assert_eq!((display["running"]["width"].clone(), display["running"]["height"].clone()), (json!(720), json!(1560)), "{display}");
        let before = phone.fake().touches().len();
        let (x, y) = page.viewport_point((720, 1560), 600, 1300).await;
        page.click_at(x, y).await;
        let p = phone.clone();
        let touch = blocking(move || p.fake().wait_record("a touch", Duration::from_secs(10), |r| r["touches"].as_array()?.get(before).cloned()));
        let (tx, ty) = (touch["x"].as_f64().unwrap(), touch["y"].as_f64().unwrap());
        assert!((tx - 600.0).abs() <= 4.0 && (ty - 1300.0).abs() <= 4.0, "a touch at the new size lands right: {touch}");
    });
}

#[test]
fn a_settings_only_change_sends_no_size_and_does_not_reload() {
    let cp = CloudPhone::start_with(json!({"settings": {"cores": 2}}));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        open_form(&page).await;
        mark_load(&page).await;
        select(&page, "Mémoire", "2048").await;
        answer_confirm(&page, true).await;
        click_apply(&page).await;
        let p = phone.clone();
        let requests = blocking(move || {
            p.fake().wait_record("the settings request", Duration::from_secs(10), |r| {
                let asked: Vec<Value> = r["requests"]["settings"].as_array()?.iter().filter(|e| e.get("request").is_some()).cloned().collect();
                (!asked.is_empty()).then_some(asked)
            })
        });
        assert_eq!(requests[0]["request"], "lavapipe 2 2048", "no size in the request: {requests:?}");
        // Android restarts with 2 GB; the form follows.
        let p = phone.clone();
        blocking(move || {
            wait_for("the new settings", Duration::from_secs(60), || {
                let s = p.try_get_json("api/v1/emulator-settings")?;
                (s["current"]["memoryMb"] == "2048" && s["request"]["state"] == "done").then_some(())
            })
        });
        page.wait_js("the form to show 2 GB", Duration::from_secs(30),
            "const d = document.querySelector('[role=dialog]'); const s = d && [...d.querySelectorAll('label')].find(l => l.innerText.startsWith('Mémoire') && l.querySelector('select')); return !!s && s.querySelector('select').value === '2048'", vec![]).await;
        assert_eq!(page.js("return !!window.__e2eLoad", vec![]).await, json!(true), "same size: the page did not reload");
    });
}

#[test]
fn the_page_can_still_post_after_a_change_restarted_the_gateway() {
    // A settings change restarts Android, so the gateway restarts with a new
    // page token. A page that did not reload still holds the old one: found
    // by this test, its next POST is refused ("Missing or invalid page
    // token: reload the page").
    let cp = CloudPhone::start_with(json!({"settings": {"cores": 2}}));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        let old = phone.page_token();
        open_form(&page).await;
        select(&page, "Mémoire", "2048").await;
        answer_confirm(&page, true).await;
        click_apply(&page).await;
        let p = phone.clone();
        let new = blocking(move || p.wait_new_token(&old, Duration::from_secs(60)));
        let page_token = page.js("return document.querySelector('meta[name=cloudphone-token]').content", vec![]).await;
        eprintln!("gateway token changed; the page holds {}", if page_token == json!(new) { "the new one" } else { "the old one" });
        let p = phone.clone();
        blocking(move || p.wait_for_android(Duration::from_secs(60)));
        page.wait_js("the form to be idle", Duration::from_secs(30),
            "const d = document.querySelector('[role=dialog]'); return !!d && !d.innerText.includes('Android redémarre') && !d.innerText.includes('en attente')", vec![]).await;
        // The page has reconnected: its state poll answers (no reconnect
        // banner) and its settings poll (every 10 s) brought the running
        // 2048 MiB, so Apply is off for an unchanged form. Choosing before
        // that would be undone when the form takes the new settings.
        page.wait_js("the page to reconnect and show the running settings", Duration::from_secs(45),
            "const banners = [...document.querySelectorAll('[role=status]')].map(b => b.innerText).join(' '); \
             const apply = [...document.querySelectorAll('[role=dialog] button')].find(b => b.innerText.trim() === 'Appliquer'); \
             return !banners.includes('se reconnecte') && !banners.includes('Android démarre') && !!apply && apply.disabled", vec![]).await;
        select(&page, "Mémoire", "4096").await;
        answer_confirm(&page, true).await;
        click_apply(&page).await;
        page.sleep(Duration::from_secs(2)).await;
        let text = page.dialog_text(P).await;
        assert!(!text.contains("403") && !text.to_lowercase().contains("token"), "the page's POST is accepted after the gateway restarted: {text}");
        // The gateway took the POST with the new token and answered it: one
        // change per 2 minutes, so this second one is refused for that, with
        // the time to wait, and nothing reaches Android.
        assert!(text.contains("Wait") || text.contains("Attendez"), "the 2-minute limit answers the second change: {text}");
        let requests = phone.fake().record()["requests"]["settings"].as_array().unwrap().iter().filter(|e| e.get("request").is_some()).count();
        assert_eq!(requests, 1, "the second change was not sent to Android");
    });
}

#[test]
fn cancelling_the_confirmation_sends_nothing() {
    let cp = CloudPhone::start_with(json!({"settings": {"cores": 2}}));
    let phone = cp.clone();
    browser_test(&cp, Options::without_video(), |page| async move {
        open_form(&page).await;
        select(&page, "Résolution", "360").await;
        answer_confirm(&page, false).await;
        click_apply(&page).await;
        page.sleep(Duration::from_secs(2)).await;
        assert_eq!(confirmations(&page).await.len(), 1);
        assert!(settings_requests(&phone).is_empty(), "nothing sent");
        assert_eq!(phone.get_json("api/v1/emulator-settings")["request"]["state"], "idle");
    });
}

#[test]
fn a_pending_change_locks_the_form_and_says_it_waits() {
    // The root service does not pick the request up (path unit stalled).
    let cp = CloudPhone::start_with(json!({"settings": {"cores": 2}, "options": {"hold_requests": true}}));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        open_form(&page).await;
        select(&page, "Mémoire", "2048").await;
        answer_confirm(&page, true).await;
        click_apply(&page).await;
        page.wait_js("the pending note", Duration::from_secs(15),
            "const d = document.querySelector('[role=dialog]'); return !!d && d.innerText.includes('Demande envoyée, en attente du serveur…')", vec![]).await;
        let disabled = page.js("return [...document.querySelectorAll('[role=dialog] select')].slice(-5).map(s => s.disabled)", vec![]).await;
        assert_eq!(disabled, json!([true, true, true, true, true]), "the form is locked while pending");
        assert!(apply_disabled(&page).await);
        // The service picks it up: applying, then done.
        phone.fake().control(json!({"hold_requests": false}));
        let p = phone.clone();
        blocking(move || {
            wait_for("the change to be done", Duration::from_secs(60), || {
                let s = p.try_get_json("api/v1/emulator-settings")?;
                (s["request"]["state"] == "done").then_some(())
            })
        });
        page.wait_js("the form to unlock", Duration::from_secs(30),
            "return [...document.querySelectorAll('[role=dialog] select')].every(s => !s.disabled)", vec![]).await;
    });
}

#[test]
fn a_change_made_from_another_device_shows_here_too() {
    let cp = CloudPhone::start_with(json!({"settings": {"cores": 2}, "options": {"hold_requests": true}}));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        open_form(&page).await;
        let response = phone.post_json("api/v1/display", &json!({"width": 360, "height": 780, "density": 160}));
        assert_eq!(response.status(), 202);
        page.wait_status("Changement de résolution", Duration::from_secs(15)).await;
        // The form follows the settings request only: a pending size change
        // made through /api/v1/display leaves it enabled (the screen is
        // covered meanwhile; an Apply would get 409).
        let locked = page.js("return [...document.querySelectorAll('[role=dialog] select')].some(s => s.disabled)", vec![]).await;
        eprintln!("form locked during another device's size change: {locked}");
    });
}

#[test]
fn a_failed_change_is_reported_in_the_form() {
    let cp = CloudPhone::start_with(json!({"settings": {"cores": 2}, "options": {"fail_next": {"settings": "renderer swangle missing"}}}));
    browser_test(&cp, Options::without_video(), |page| async move {
        open_form(&page).await;
        select(&page, "Mémoire", "2048").await;
        answer_confirm(&page, true).await;
        click_apply(&page).await;
        page.wait_js("the failure", Duration::from_secs(30),
            "const d = document.querySelector('[role=dialog]'); return !!d && d.innerText.includes('Échec : renderer swangle missing')", vec![]).await;
        // Android keeps running; the form is usable again. The cover goes
        // with the next state poll (the form polls its own route).
        page.wait_no_status("Changement des réglages", Duration::from_secs(10)).await;
        assert!(page.banners().await.is_empty(), "{:?}", page.banners().await);
        let disabled = page.js("return [...document.querySelectorAll('[role=dialog] select')].some(s => s.disabled)", vec![]).await;
        assert_eq!(disabled, json!(false));
    });
}

#[test]
fn a_refused_request_shows_the_servers_reason() {
    // A change already pending (from another device) when this page, which
    // has not refreshed yet, applies its own: the gateway refuses with 409.
    let cp = CloudPhone::start_with(json!({"settings": {"cores": 2}, "options": {"hold_requests": true}}));
    let phone = cp.clone();
    browser_test(&cp, Options::without_video(), |page| async move {
        open_form(&page).await;
        select(&page, "Mémoire", "2048").await;
        let response = phone.post_json("api/v1/emulator-settings", &json!({"renderer": "lavapipe", "cores": 2, "memoryMb": 3072}));
        assert_eq!(response.status(), 202);
        answer_confirm(&page, true).await;
        if apply_disabled(&page).await {
            eprintln!("the form refreshed before the click: nothing to refuse");
            return;
        }
        click_apply(&page).await;
        page.wait_js("the refusal", Duration::from_secs(10),
            "const d = document.querySelector('[role=dialog]'); return !!d && d.innerText.includes('A change is already in progress')", vec![]).await;
    });
}
