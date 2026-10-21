//! English means English everywhere: with English chosen in the options,
//! the information panel (both tabs), the options panel with the Slayer
//! Legend plugin unfolded, and each of its dialogs, show no French: no
//! accented letter, no French word, in the visible text nor in the labels a
//! screen reader reads. Also on the gateway's non-trivial states (the
//! watchdog paused, the mine on, a refused mode, a switch on hold while the
//! user plays). Data values
//! are excepted (a language's own name). Log records are English at their
//! source: the page's own (Client tab) are checked here; the server's are
//! its data, left out.
use cloudphone_e2e::browser::{blocking, browser_test, en, Options, Page};
use cloudphone_e2e::*;
use fantoccini::Locator;
use serde_json::{json, Value};
use std::time::Duration;

const SLAYER_LEGEND: &str = "05-plugins/slayer-legend";
const MODE: &str = "api/v1/plugins/slayer-legend/mode";
const WATCHDOG: &str = "api/v1/plugins/slayer-legend/watchdog";

/// Every text shown or named inside the elements `arguments[0]` (a CSS
/// selector) finds: text nodes (not those folded away), aria-label, title,
/// placeholder, alt. Log records ([data-level]) left out when arguments[1]
/// is true.
const TEXTS: &str = r#"
const skipLogs = arguments[1];
const out = [];
const skipped = (el) => skipLogs && el.closest('[data-level]');
for (const root of document.querySelectorAll(arguments[0])) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const el = node.parentElement;
    if (!el || skipped(el) || el.closest('script,style')) continue;
    if (el.closest('details:not([open]) > :not(summary)')) continue;
    const text = node.textContent.trim();
    if (text) out.push(text);
  }
  for (const el of root.querySelectorAll('*')) {
    if (skipped(el)) continue;
    for (const name of ['aria-label', 'title', 'placeholder', 'alt']) {
      const value = el.getAttribute(name);
      if (value && value.trim()) out.push(value.trim());
    }
  }
}
return out;
"#;

/// French words that are no English words, lower case.
const FRENCH_WORDS: &[&str] = &[
    "le", "la", "les", "des", "du", "de", "un", "une", "et", "est", "pas", "pour", "sur", "avec", "dans", "en",
    "au", "aux", "ou", "ne", "sans", "par", "mais", "cette", "ce", "ces", "qui", "que", "sa", "ses", "mes",
    "tu", "il", "elle", "nous", "vous", "leur", "deux", "oui", "non", "rien", "aucun", "aucune", "jeu",
    "libre", "choisir", "choisis", "fermer", "touchez", "touche", "serveur", "appareil",
];

/// Data values, shown as they are in either language.
const DATA: &[&str] = &["Français"];

fn french(text: &str) -> bool {
    if DATA.contains(&text) {
        return false;
    }
    let accented = text.chars().any(|c| "àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒÆ«»".contains(c));
    let words = text
        .split(|c: char| !(c.is_alphanumeric() || c == '-' || c == '\'' || c == '’'))
        .any(|w| !w.is_empty() && FRENCH_WORDS.contains(&w.to_lowercase().as_str()));
    accented || words
}

/// The French texts in `css`, each prefixed with `place`.
async fn french_in(page: &Page, place: &str, css: &str, skip_logs: bool) -> Vec<String> {
    let texts = page.js(TEXTS, vec![json!(css), json!(skip_logs)]).await;
    let mut found: Vec<String> = texts.as_array().into_iter().flatten()
        .filter_map(Value::as_str).filter(|t| french(t)).map(|t| format!("{place}: {t}")).collect();
    found.dedup();
    found
}

/// A French browser, English chosen in the options as a user does, the
/// panel closed again.
async fn choose_english(page: &Page) {
    let panel = page.open_options().await;
    page.control(&panel, "Langue").await.select_by_value("en").await.unwrap();
    page.wait_for_label(en::OPTIONS, Duration::from_secs(15)).await;
    page.click_label(en::CLOSE).await;
    page.wait_no_dialog().await;
}

/// The options panel open, every section of the plugin unfolded, its
/// rows filled.
async fn open_plugin(page: &Page) {
    page.open_options().await;
    page.wait_js("the plugin's options", Duration::from_secs(15),
        "const d = document.querySelector('[role=dialog]'); return !!d && d.innerText.includes('Mode and farming')", vec![]).await;
    page.js("document.querySelectorAll('[role=dialog] details').forEach(d => { d.open = true; })", vec![]).await;
    page.wait_dialog_value(en::OPTIONS_PANEL, "Stage", Duration::from_secs(15), |_| true).await;
}

const LAST_DIALOG_CLOSE: &str = "[...document.querySelectorAll('[role=dialog]')].pop().querySelector('button[aria-label=Close]').click()";

/// Opens each of the plugin's dialogs in turn (its Configure buttons):
/// the French texts of the panel and the dialog.
async fn french_in_dialogs(page: &Page, place: &str) -> Vec<String> {
    const CONFIGURE: &str = "[...document.querySelectorAll('[role=dialog] button')].filter(b => b.innerText.trim() === 'Configure')";
    let count = page.js(&format!("return {CONFIGURE}.length"), vec![]).await.as_u64().unwrap_or(0);
    assert!(count >= 2, "the plugin's dialog buttons: {count}");
    let mut found = Vec::new();
    for index in 0..count {
        page.js(&format!("{CONFIGURE}[arguments[0]].click()"), vec![json!(index)]).await;
        let name = page.wait_js("the plugin's dialog", Duration::from_secs(10),
            "const d = [...document.querySelectorAll('[role=dialog]')]; return d.length >= 2 ? d[d.length - 1].getAttribute('aria-label') : null",
            vec![]).await;
        page.sleep(Duration::from_secs(2)).await;
        found.extend(french_in(page, &format!("{place}, dialog {name}"), "[role=dialog]", true).await);
        page.js(LAST_DIALOG_CLOSE, vec![]).await;
        page.wait_js("the dialog closed", Duration::from_secs(10),
            "return document.querySelectorAll('[role=dialog]').length === 1", vec![]).await;
    }
    found
}

#[test]
fn in_english_the_panels_the_plugin_and_its_dialogs_show_no_french() {
    let cp = CloudPhone::start_with(json!({"plugins": [SLAYER_LEGEND]}));
    browser_test(&cp, Options::without_video(), |page| async move {
        choose_english(&page).await;
        let mut seen = french_in(&page, "page", "body", true).await;
        // The information panel's two tabs: the page's own records included.
        page.open_info(en::CLIENT_TAB).await;
        page.sleep(Duration::from_secs(2)).await;
        seen.extend(french_in(&page, "Client", "[role=dialog]", false).await);
        page.open_info(en::SERVER_TAB).await;
        page.wait_js("the server's figures", Duration::from_secs(15),
            "const d = document.querySelector('[role=dialog]'); return !!d && d.innerText.includes('Machine')", vec![]).await;
        page.sleep(Duration::from_secs(2)).await;
        seen.extend(french_in(&page, "Server", "[role=dialog]", true).await);
        page.click_label(en::CLOSE).await;
        page.wait_no_dialog().await;
        // The options panel, the plugin unfolded, then each of its dialogs.
        open_plugin(&page).await;
        page.sleep(Duration::from_secs(3)).await;
        seen.extend(french_in(&page, "Options", "[role=dialog]", true).await);
        seen.extend(french_in_dialogs(&page, "Options").await);
        assert!(seen.is_empty(), "French shown in English:\n{}", seen.join("\n"));
    });
}

/// The plugin's État row ("Status" in English, the page's own word).
async fn state_row(page: &Page) -> String {
    page.dialog_value(en::OPTIONS_PANEL, "Status").await.unwrap_or_default()
}

async fn open_mine_dialog(page: &Page) {
    page.client.find(Locator::XPath(
        "//div[@role='dialog']//div[label[normalize-space()='Closed Mine']]//button[normalize-space()='Configure']"))
        .await.unwrap().click().await.unwrap();
    page.wait_dialog("Closed Mine").await;
}

#[test]
fn in_english_the_gateways_states_show_no_french() {
    let cp = CloudPhone::start_with(json!({"plugins": [SLAYER_LEGEND]}));
    let phone = cp.clone();
    browser_test(&cp, Options::without_video(), |page| async move {
        choose_english(&page).await;
        open_plugin(&page).await;
        let mut seen = Vec::new();
        // The watchdog paused while the user plays (an input), as the
        // État row's end says it at the page's next ask (every 15 s).
        let p = phone.clone();
        blocking(move || {
            assert_eq!(p.post_json("api/v1/input", &json!({})).status(), 200);
            wait_for("the watchdog paused", Duration::from_secs(60), || {
                let state = p.try_get_json(WATCHDOG)?;
                (state["status"]["template"] == "En pause : l’utilisateur joue").then_some(())
            });
        });
        page.sleep(Duration::from_secs(16)).await;
        let paused = state_row(&page).await;
        seen.extend(french_in(&page, &format!("watchdog paused ({paused})"), "[role=dialog]", true).await);
        // The mine on, configured and chosen in the page (no game on the
        // fake: its own status), at two looks.
        open_mine_dialog(&page).await;
        let floor = page.control("Closed Mine", "Floor to farm").await;
        floor.send_keys("161").await.unwrap();
        page.control("Closed Mine", "Area to farm").await.select_by_value("1").await.unwrap();
        page.js(LAST_DIALOG_CLOSE, vec![]).await;
        let before = state_row(&page).await;
        page.client.find(Locator::XPath(
            "//div[@role='dialog']//label[normalize-space()='Closed Mine']/input"))
            .await.unwrap().click().await.unwrap();
        let first = page.wait_dialog_value(en::OPTIONS_PANEL, "Status", Duration::from_secs(30), |v| v != before).await;
        seen.extend(french_in(&page, &format!("mine on ({first})"), "[role=dialog]", true).await);
        page.sleep(Duration::from_secs(12)).await;
        let later = state_row(&page).await;
        seen.extend(french_in(&page, &format!("mine on ({later})"), "[role=dialog]", true).await);
        // A mode the gateway refuses: the mine's floor out of range.
        open_mine_dialog(&page).await;
        let floor = page.control("Closed Mine", "Floor to farm").await;
        floor.clear().await.unwrap();
        floor.send_keys("99999").await.unwrap();
        page.js(LAST_DIALOG_CLOSE, vec![]).await;
        let refused = page.wait_dialog_value(en::OPTIONS_PANEL, "Status", Duration::from_secs(15), |v| v != later).await;
        seen.extend(french_in(&page, &format!("refused ({refused})"), "[role=dialog]", true).await);
        // The floor set right again: the page's error goes with the change.
        open_mine_dialog(&page).await;
        let floor = page.control("Closed Mine", "Floor to farm").await;
        floor.clear().await.unwrap();
        floor.send_keys("161").await.unwrap();
        page.js(LAST_DIALOG_CLOSE, vec![]).await;
        page.wait_dialog_value(en::OPTIONS_PANEL, "Status", Duration::from_secs(15), |v| v != refused).await;
        // A switch on hold while the user plays.
        let p = phone.clone();
        blocking(move || {
            assert_eq!(p.post_json("api/v1/input", &json!({})).status(), 200);
            assert_eq!(p.post_json(MODE, &json!({"mode": "mpw4", "stage4": 31})).status(), 200);
            wait_for("the switch on hold", Duration::from_secs(20), || (!p.try_get_json(MODE)?["hold"].is_null()).then_some(()));
        });
        let held = page.wait_dialog_value(en::OPTIONS_PANEL, "Status", Duration::from_secs(20), |v| v.contains("on hold")).await;
        seen.extend(french_in(&page, &format!("on hold ({held})"), "[role=dialog]", true).await);
        seen.dedup();
        assert!(seen.is_empty(), "French shown in English:\n{}", seen.join("\n"));
    });
}
