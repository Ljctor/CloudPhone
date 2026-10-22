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
const FUTURE: &str = "tests/fake-emulator/plugins/e2e-future";
const SLAYER_LEGEND: &str = "05-plugins/slayer-legend";
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
fn a_plugin_the_gateway_refused_is_shown_with_its_error() {
    let cp = CloudPhone::start_with(json!({"plugins": [PROBE, FUTURE]}));
    browser_test(&cp, Options::default(), |page| async move {
        open_plugins(&page).await;
        let text = page.dialog_text(O).await;
        assert!(text.contains("Greffon futur"), "the refused plugin is named: {text}");
        assert!(text.contains("Échec : written for plugin API 2"), "with the gateway's error: {text}");
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

/// The buttons in the options panel's row of the plugin option labelled `label`.
async fn row_buttons(page: &Page, label: &str) -> serde_json::Value {
    let row = page.control(O, label).await;
    page.js("return [...arguments[0].closest('label').parentElement.querySelectorAll('button')].map(b => b.innerText.trim())",
        vec![serde_json::to_value(&row).unwrap()]).await
}

#[test]
fn a_dialog_row_with_nothing_to_configure_has_no_button() {
    let cp = probe_page();
    browser_test(&cp, Options::without_video(), |page| async move {
        open_plugins(&page).await;
        assert_eq!(row_buttons(&page, "Choix A").await, json!(["Configurer"]), "a row with options opens them");
        assert_eq!(row_buttons(&page, "Choix B").await, json!([]), "options: [] shows no button");
    });
}

#[test]
fn a_disabled_dialog_radio_cannot_be_chosen_until_it_is_enabled() {
    let cp = probe_page();
    browser_test(&cp, Options::without_video(), |page| async move {
        open_plugins(&page).await;
        let a = page.control_state(&page.control(O, "Choix A").await).await;
        let b = page.control_state(&page.control(O, "Choix B").await).await;
        assert_eq!((a["checked"].clone(), a["disabled"].clone()), (json!(true), json!(false)), "the default: {a}");
        assert_eq!((b["checked"].clone(), b["disabled"].clone()), (json!(false), json!(true)), "disabled() is true: {b}");
        // A click on it does nothing (WebDriver may or may not refuse it).
        let _ = page.control(O, "Choix B").await.click().await;
        assert_eq!(page.control_state(&page.control(O, "Choix B").await).await["checked"], false);
        assert_eq!(page.stored_settings().await["plugins"]["e2e-probe"]["pick"], serde_json::Value::Null, "nothing stored");
        // Its condition comes true in the other row's dialog.
        let configure = page.client.find(Locator::XPath(
            "//div[@role='dialog']//label[contains(., 'Choix A')]/following-sibling::button")).await.unwrap();
        configure.click().await.unwrap();
        let settings = "Réglages du choix A";
        page.wait_dialog(settings).await;
        page.control(settings, "Autoriser B").await.click().await.unwrap();
        page.client.find(Locator::Css(&format!("[role=dialog][aria-label='{settings}'] [aria-label='Fermer']"))).await.unwrap()
            .click().await.unwrap();
        page.wait_js("the radio enabled", Duration::from_secs(5),
            "const l = [...document.querySelectorAll('[role=dialog] label')].find(l => l.innerText.trim() === 'Choix B'); \
             return !!l && !l.control.disabled", vec![]).await;
        page.control(O, "Choix B").await.click().await.unwrap();
        let b = page.control_state(&page.control(O, "Choix B").await).await;
        assert_eq!(b["checked"], true, "{b}");
        assert_eq!(page.control_state(&page.control(O, "Choix A").await).await["checked"], false, "one of the group");
        assert_eq!(page.stored_settings().await["plugins"]["e2e-probe"]["pick"], "b");
    });
}

/// The grid drawn in the dialog `dialog` (a plugin's 'grid' option), once
/// it has `cells` visible cells: {slots, cells, filled, empty, columns,
/// rows, sizes}, sizes the distinct sizes of the visible cells.
async fn grid_shape(page: &Page, dialog: &str, cells: usize) -> serde_json::Value {
    page.wait_js("the engraving grid", Duration::from_secs(10),
        "const d = [...document.querySelectorAll('[role=dialog]')].find(d => d.getAttribute('aria-label') === arguments[0]); \
         const g = d && d.querySelector('[data-plugin-grid]'); if (!g) return null; \
         const shown = [...g.querySelectorAll('[data-cell]')]; if (shown.length !== arguments[1]) return null; \
         const box = g.getBoundingClientRect(); \
         const at = shown.map(c => c.getBoundingClientRect()); \
         const xs = new Set(at.map(r => Math.round(r.left - box.left))), ys = new Set(at.map(r => Math.round(r.top - box.top))); \
         return {slots: g.children.length, cells: shown.length, \
                 filled: shown.filter(c => c.dataset.cell === 'filled').length, \
                 empty: shown.filter(c => c.dataset.cell === 'empty').length, \
                 columns: xs.size, rows: ys.size, \
                 sizes: [...new Set(at.map(r => `${Math.round(r.width)}x${Math.round(r.height)}`))], \
                 text: g.innerText.trim()}",
        vec![json!(dialog), json!(cells)]).await
}

/// The `<option>` values of the select labelled `label` in the panel `dialog`.
async fn option_values(page: &Page, dialog: &str, label: &str) -> Vec<String> {
    let state = page.control_state(&page.control(dialog, label).await).await;
    state["options"].as_array()
        .map(|o| o.iter().filter_map(|v| v.as_str()).map(|v| v.split(':').next().unwrap().to_string()).collect())
        .unwrap_or_default()
}

/// Waits until the select labelled `label` has an option `value`.
async fn wait_option(page: &Page, dialog: &str, label: &str, value: &str) -> Vec<String> {
    let start = std::time::Instant::now();
    loop {
        let values = option_values(page, dialog, label).await;
        if values.iter().any(|v| v == value) {
            return values;
        }
        assert!(start.elapsed() < Duration::from_secs(10), "{label}: no option {value:?} in {values:?}");
        page.sleep(Duration::from_millis(300)).await;
    }
}

#[test]
fn slayer_legends_mpw18_loadout_is_chosen_in_its_dialog_and_saved_on_change() {
    let cp = CloudPhone::start_with(json!({"plugins": [SLAYER_LEGEND]}));
    let phone = cp.clone();
    browser_test(&cp, Options::without_video(), |page| async move {
        page.open_options().await;
        page.wait_js("the plugin's options", Duration::from_secs(15),
            "const d = document.querySelector('[role=dialog]'); return !!d && d.innerText.includes('Mode par défaut')",
            vec![]).await;
        page.client.find(Locator::XPath(
            "//div[@role='dialog']//label[normalize-space()='Farming mpw18']/following-sibling::button")).await.unwrap()
            .click().await.unwrap();
        let settings = "Farming mpw18";
        page.wait_dialog(settings).await;
        page.control(settings, "Préréglage de combat").await.select_by_value("III").await.unwrap();
        // The weapons and their variants come from the gateway (engravings.json).
        wait_option(&page, settings, "Soul Weapon", "32").await;
        page.control(settings, "Soul Weapon").await.select_by_value("32").await.unwrap();
        let variants = wait_option(&page, settings, "Gravure", "Gold-maxed").await;
        assert_eq!(variants, ["", "Balanced", "Crit", "Gold-maxed", "Gold-balanced"]);
        page.control(settings, "Gravure").await.select_by_value("Gold-maxed").await.unwrap();
        // Read-only: Ambition's grid, its 16 cells filled by four vertical
        // bars.
        let grid = grid_shape(&page, settings, 16).await;
        assert_eq!((grid["slots"].as_u64(), grid["filled"].as_u64(), grid["empty"].as_u64()),
                   (Some(25), Some(16), Some(0)), "{grid}");
        // Saved on change, with no button and no row saying so.
        let p = phone.clone();
        blocking(move || wait_for("the loadout saved", Duration::from_secs(10), || {
            let saved = p.try_get_json("api/v1/plugins/slayer-legend/loadout")?;
            (saved["loadouts"]["mpw18"]["soul_weapon"] == json!({"id": 32, "variant": "Gold-maxed"})).then_some(())
        }));
        let text = page.dialog_text(settings).await;
        for gone in ["Enregistrer", "Enregistré", "Pièces nécessaires", "Source", "Équipement de combat"] {
            assert!(!text.lines().any(|l| l.trim() == gone), "no {gone:?}: {text}");
        }
        // Vision: pieces keep their dropped orientation ("per-piece"), so
        // its Gold-balanced exists; its grid shows its 16 active cells, not
        // a square of 25 (columns 1 to 4 of rows 0 to 4), all the same
        // fixed size, and no warning but the grids to check in game.
        page.control(settings, "Soul Weapon").await.select_by_value("36").await.unwrap();
        let variants = wait_option(&page, settings, "Gravure", "Gold-balanced").await;
        assert_eq!(variants, ["", "Atk", "Balanced", "Gold-maxed", "Gold-balanced"]);
        page.control(settings, "Gravure").await.select_by_value("Gold-balanced").await.unwrap();
        let grid = grid_shape(&page, settings, 16).await;
        assert_eq!((grid["slots"].as_u64(), grid["filled"].as_u64(), grid["columns"].as_u64(), grid["rows"].as_u64()),
                   (Some(25), Some(16), Some(4), Some(5)), "{grid}");
        assert_ne!(grid["cells"].as_u64(), Some(25), "not a square: {grid}");
        assert_eq!(grid["sizes"].as_array().map(|s| s.len()), Some(1), "fixed-size cells: {grid}");
        assert_eq!(grid["text"], "", "no emoji: {grid}");
        assert_eq!(page.dialog_value(settings, "Attention").await, None);
        // Choosing Vision's variant saves it too; the test then waits for
        // it before checking what was kept.
        let p = phone.clone();
        blocking(move || wait_for("the loadout saved", Duration::from_secs(10), || {
            let saved = p.try_get_json("api/v1/plugins/slayer-legend/loadout")?;
            (saved["loadouts"]["mpw18"]["soul_weapon"] == json!({"id": 36, "variant": "Gold-balanced"})).then_some(())
        }));
        let p = phone.clone();
        let saved = blocking(move || p.get_json("api/v1/plugins/slayer-legend/loadout"));
        assert_eq!(saved["loadouts"]["mpw18"]["preset"], "III", "{saved}");
        assert_eq!(saved["loadouts"]["mpw18"]["soul_weapon"], json!({"id": 36, "variant": "Gold-balanced"}), "{saved}");
        assert_eq!(saved["loadouts"]["mpw4"]["soul_weapon"], serde_json::Value::Null, "{saved}");
    });
}

#[test]
fn slayer_legends_saved_loadout_survives_a_change_from_a_fresh_browser() {
    let cp = CloudPhone::start_with(json!({"plugins": [SLAYER_LEGEND]}));
    let saved = json!({"mode": "mpw18", "stage": 940, "preset": "III", "soul_weapon": {"id": 32, "variant": "Gold-maxed"}});
    assert_eq!(cp.post_json("api/v1/plugins/slayer-legend/loadout", &saved).status(), 200);
    let before = cp.get_json("api/v1/plugins/slayer-legend/loadout");
    let phone = cp.clone();
    // A browser with no settings of its own: its selectors show the server's loadout.
    browser_test(&cp, Options::without_video(), |page| async move {
        page.open_options().await;
        page.wait_js("the plugin's options", Duration::from_secs(15),
            "const d = document.querySelector('[role=dialog]'); return !!d && d.innerText.includes('Mode par défaut')",
            vec![]).await;
        page.client.find(Locator::XPath(
            "//div[@role='dialog']//label[normalize-space()='Farming mpw18']/following-sibling::button")).await.unwrap()
            .click().await.unwrap();
        let settings = "Farming mpw18";
        page.wait_dialog(settings).await;
        wait_option(&page, settings, "Gravure", "Gold-maxed").await;
        for (label, value) in [("Préréglage de combat", "III"), ("Soul Weapon", "32"), ("Gravure", "Gold-maxed")] {
            let state = page.control_state(&page.control(settings, label).await).await;
            assert_eq!(state["value"], value, "{label} shows the saved value: {state}");
        }
        assert_eq!(page.stored_settings().await["plugins"]["slayer-legend"]["mpw18Preset"], serde_json::Value::Null,
            "nothing chosen in this browser");
        // A change here saves that field alone, at once: the rest is kept.
        page.js("window.__posts = []; const f = window.fetch; window.fetch = (url, init) => { \
                 if (String(url).includes('/loadout') && init && init.method === 'POST') window.__posts.push(init.body); \
                 return f(url, init); }; return true", vec![]).await;
        page.control(settings, "Préréglage de combat").await.select_by_value("IV").await.unwrap();
        page.wait_js("the POST sent", Duration::from_secs(10), "return window.__posts.length === 1", vec![]).await;
        let sent = page.js("return JSON.parse(window.__posts[0])", vec![]).await;
        assert_eq!(sent, json!({"mode": "mpw18", "preset": "IV"}), "only what was chosen here");
        page.sleep(Duration::from_millis(800)).await;
        assert_eq!(page.js("return window.__posts.length", vec![]).await, json!(1), "once, debounced");
        let p = phone.clone();
        let after = blocking(move || p.get_json("api/v1/plugins/slayer-legend/loadout"));
        let mut expected = before.clone();
        expected["loadouts"]["mpw18"]["preset"] = json!("IV");
        assert_eq!(after, expected, "the rest of the saved loadout is kept");
        assert_eq!(after["loadouts"]["mpw18"]["stage"], 940, "{after}");
    });
}

#[test]
fn slayer_legends_default_mode_is_chosen_and_saved_on_change() {
    let cp = CloudPhone::start_with(json!({"plugins": [SLAYER_LEGEND]}));
    let phone = cp.clone();
    browser_test(&cp, Options::without_video(), |page| async move {
        page.open_options().await;
        page.wait_js("the plugin's options", Duration::from_secs(15),
            "const d = document.querySelector('[role=dialog]'); return !!d && d.innerText.includes('Mode par défaut')", vec![]).await;
        let control = page.control(O, "Mode par défaut").await;
        // mpw18 by default; mpw4 not offered while its stage is not chosen, never the mine.
        let state = page.control_state(&control).await;
        assert_eq!(state["value"], "mpw18", "{state}");
        assert_eq!(state["options"], json!(["mpw18:Farming mpw18", "free:Jeu libre"]), "{state}");
        control.select_by_value("free").await.unwrap();
        let p = phone.clone();
        blocking(move || wait_for("the default mode saved", Duration::from_secs(10), || {
            let mode = p.try_get_json("api/v1/plugins/slayer-legend/mode")?;
            (mode["default"] == "free").then_some(())
        }));
        assert_eq!(page.stored_settings().await["plugins"]["slayer-legend"]["defaultMode"], "free");
        // The gateway refuses mpw4 as the default while its stage is not chosen.
        let p = phone.clone();
        let status = blocking(move || p.post_json("api/v1/plugins/slayer-legend/mode",
                                                  &json!({"mode": "mpw18", "default": "mpw4"})).status());
        assert_eq!(status, 400);
    });
}

#[test]
fn slayer_legends_mode_radio_follows_the_gateway_when_a_timed_mode_ends() {
    let cp = CloudPhone::start_with(json!({"plugins": [SLAYER_LEGEND]}));
    let phone = cp.clone();
    browser_test(&cp, Options::without_video(), |page| async move {
        page.open_options().await;
        page.wait_js("the plugin's options", Duration::from_secs(15),
            "const d = document.querySelector('[role=dialog]'); return !!d && d.innerText.includes('Jeu libre')", vec![]).await;
        page.js("window.__modes = []; const f = window.fetch; window.fetch = (url, init) => { \
                 if (String(url).endsWith('/mode') && init && init.method === 'POST') window.__modes.push(init.body); \
                 return f(url, init); }; return true", vec![]).await;
        // Free play for 15 s, chosen elsewhere (another browser): the radio follows it.
        let p = phone.clone();
        let until = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs() + 15;
        let status = blocking(move || p.post_json("api/v1/plugins/slayer-legend/mode",
                                                  &json!({"mode": "free", "until": until})).status());
        assert_eq!(status, 200);
        page.wait_js("the radio on free play", Duration::from_secs(25),
            "const l = [...document.querySelectorAll('[role=dialog] label')].find(l => l.innerText.trim() === 'Jeu libre'); \
             return !!l && l.control.checked", vec![]).await;
        // Its timer ends: the gateway is back on mpw18, and so is the radio.
        page.wait_js("the radio back on mpw18", Duration::from_secs(45),
            "const l = [...document.querySelectorAll('[role=dialog] label')]\
             .find(l => l.innerText.trim() === 'Farming mpw18'); return !!l && l.control.checked", vec![]).await;
        assert_eq!(page.stored_settings().await["plugins"]["slayer-legend"]["mode"], "mpw18");
        let p = phone.clone();
        assert_eq!(blocking(move || p.get_json("api/v1/plugins/slayer-legend/mode"))["mode"], "mpw18");
        page.sleep(Duration::from_secs(1)).await;
        assert_eq!(page.js("return window.__modes", vec![]).await, json!([]), "the page sent no mode back");
    });
}

#[test]
fn slayer_legends_backoff_wait_shows_in_the_state_row_with_retry() {
    // A real failure on the fake: the game asks to sign in and Google's
    // chooser lists two accounts, so the watchdog's relaunch stops.
    let app = json!({"package": "com.gear2.growslayer", "activity": "com.google.firebase.MessagingUnityPlayerActivity",
        "state": "signin", "start_seconds": 8, "sign_in_button": [0.245, 0.722, 0.755, 0.770],
        "accounts": ["player@example.com", "other@example.com"],
        "picture": [[0.36, 0.012, 0.42, 0.036, [40, 200, 60]], [0.0, 0.972, 1.0, 0.998, [225, 225, 225]]],
        "sign_in_picture": [[0.0, 0.0, 1.0, 1.0, [90, 60, 35]],
            [0.245, 0.722, 0.755, 0.770, [235, 235, 235]], [0.285, 0.738, 0.325, 0.756, [65, 131, 239]],
            [0.37, 0.742, 0.66, 0.752, [117, 117, 116]],
            [0.245, 0.788, 0.755, 0.836, [235, 235, 235]], [0.28, 0.802, 0.32, 0.822, [0, 0, 0]],
            [0.37, 0.808, 0.66, 0.818, [0, 0, 0]]]});
    let cp = CloudPhone::start_with(json!({"plugins": [SLAYER_LEGEND], "options": {"app": app}}));
    wait_for("the relaunch's backoff", Duration::from_secs(150), || {
        let state = cp.try_get_json("api/v1/plugins/slayer-legend/watchdog")?;
        (state["waiting"] == json!(["relaunch"])).then_some(())
    });
    let phone = cp.clone();
    browser_test(&cp, Options::without_video(), |page| async move {
        page.open_options().await;
        // The selected mode's État row: the backoff's wait, « Réessayer » inline.
        let state = page.wait_dialog_value(O, "État", Duration::from_secs(40),
            |v| v.contains(" · relance du jeu dans ") && v.ends_with(" min Réessayer")).await;
        assert!(state.starts_with("Farming mpw18 · "), "{state}");
        page.js("window.__retries = []; const f = window.fetch; window.fetch = async (url, init) => { \
                 const r = await f(url, init); \
                 if (String(url).endsWith('/watchdog/retry')) window.__retries.push({headers: init.headers, \
                   body: JSON.parse(init.body), answer: await r.clone().json()}); \
                 return r; }; return true", vec![]).await;
        page.client.find(Locator::XPath(
            "//div[@role='dialog']//div[span[normalize-space()='État']]//button[normalize-space()='Réessayer']"))
            .await.unwrap().click().await.unwrap();
        page.wait_js("the retry POST", Duration::from_secs(10), "return window.__retries.length === 1", vec![]).await;
        let sent = page.js("return window.__retries[0]", vec![]).await;
        let token = page.js("return document.querySelector('meta[name=\"cloudphone-token\"]').content", vec![]).await;
        assert_eq!(sent["headers"]["X-CloudPhone-Token"], token, "with the page token: {sent}");
        assert_eq!(sent["body"], json!({"kind": "relaunch"}));
        assert_eq!(sent["answer"]["counters"]["next_attempt"], json!({}), "{sent}");
        assert_eq!(sent["answer"]["waiting"], json!([]), "{sent}");
        let p = phone.clone();
        let records = blocking(move || p.get_json("api/v1/logs"));
        assert!(records["records"].as_array().unwrap().iter()
            .any(|r| r["text"] == "Réessayer maintenant : relance du jeu"), "{records}");
    });
}

/// The summaries of the Slayer Legend plugin's sections, in order, with
/// whether each is open.
async fn slayer_sections(page: &Page) -> serde_json::Value {
    page.js("const p = [...document.querySelectorAll('[role=dialog] details')].find(d => d.querySelector(':scope > summary').innerText.trim() === 'Slayer Legend'); \
             return p ? [...p.querySelectorAll(':scope > details')].map(d => [d.querySelector(':scope > summary').innerText.trim(), d.open]) : null",
        vec![]).await
}

const OPEN_DEBUG: &str = "[...document.querySelectorAll('[role=dialog] summary')].find(s => s.innerText.trim() === 'Debug & développement').click()";

#[test]
fn slayer_legends_debug_section_is_last_folded_and_holds_the_developer_rows_and_its_log() {
    let cp = CloudPhone::start_with(json!({"plugins": [SLAYER_LEGEND]}));
    let phone = cp.clone();
    browser_test(&cp, Options::without_video(), |page| async move {
        page.open_options().await;
        page.wait_js("the plugin's options", Duration::from_secs(15),
            "const d = document.querySelector('[role=dialog]'); return !!d && d.innerText.includes('Mode et farming')", vec![]).await;
        let sections = slayer_sections(&page).await;
        let list = sections.as_array().unwrap_or_else(|| panic!("{sections}"));
        assert_eq!(list.last(), Some(&json!(["Debug & développement", false])), "last and folded: {sections}");
        let names: Vec<&str> = list.iter().map(|s| s[0].as_str().unwrap()).collect();
        assert_eq!(names, ["Mode et farming", "Gold", "Émeraudes", "Diamants", "Debug & développement"], "{sections}");
        // Icons drawn by the plugin: its own before its title, and the game's
        // currencies before theirs.
        let icons = page.wait_js("the icons drawn", Duration::from_secs(10),
            "const p = [...document.querySelectorAll('[role=dialog] details')].find(d => d.querySelector(':scope > summary').innerText.trim() === 'Slayer Legend'); \
             if (!p) return null; const drawn = (s) => { const i = s.querySelector(':scope > img'); return !!i && i.complete && i.naturalWidth > 0; }; \
             const r = [drawn(p.querySelector(':scope > summary')), ...[...p.querySelectorAll(':scope > details > summary')].filter(drawn).map(s => s.innerText.trim())]; \
             return r.length === 4 ? r : null", vec![]).await;
        assert_eq!(icons, json!([true, "Gold", "Émeraudes", "Diamants"]));
        // The stage in one row under État; the rows for the developer, or
        // that said nothing, are gone.
        page.wait_dialog_value(O, "Stage", Duration::from_secs(15), |_| true).await;
        let lines = page.dialog_lines(O).await;
        let state = lines.iter().position(|l| l == "État").unwrap_or_else(|| panic!("{lines:#?}"));
        assert_eq!(lines.get(state + 2).map(String::as_str), Some("Stage"), "{lines:#?}");
        for gone in ["Jeu", "Stage sélectionné", "Monstres par vague", "Équipement lâché", "Couleur des âmes", "Minuteur",
                     "Plumes", "Farming mpw18 (par défaut)", "Lancer le jeu", "Lancement"] {
            assert!(!lines.iter().any(|l| l == gone), "no {gone:?}: {lines:#?}");
        }
        assert!(!lines.iter().any(|l| l.contains("à confirmer") || l.contains("économie d’énergie ?")), "{lines:#?}");
        for hidden in ["Écran détecté", "Enregistrer mes parcours", "Parcours enregistrés", "Bail", "Surveillance",
                       "Détection du compteur", "Navigation"] {
            assert!(!lines.iter().any(|l| l == hidden), "{hidden:?} not shown while folded: {lines:#?}");
        }
        // A record of the plugin's: its lease taken.
        let p = phone.clone();
        let lease = json!({"holder": "agent", "reason": "réglages", "seconds": 600});
        assert_eq!(blocking(move || p.post_json("api/v1/plugins/slayer-legend/lease", &lease).status().as_u16()), 200);
        page.js(OPEN_DEBUG, vec![]).await;
        page.wait_dialog_value(O, "Bail", Duration::from_secs(25), |v| v == "agent (réglages)").await;
        let lines = page.dialog_lines(O).await;
        for shown in ["Écran détecté", "Enregistrer mes parcours", "Parcours enregistrés", "Surveillance", "Niveau"] {
            assert!(lines.iter().any(|l| l == shown), "{shown:?} in the debug section: {lines:#?}");
        }
        let log = page.wait_js("the plugin's record in its log", Duration::from_secs(20),
            "const p = [...document.querySelectorAll('[role=dialog] details')].find(d => d.querySelector(':scope > summary').innerText.trim() === 'Debug & développement'); \
             const r = p ? [...p.querySelectorAll('[data-level]')].map(e => e.innerText) : []; \
             return r.some(t => t.includes('lease taken by agent')) ? r : null", vec![]).await;
        assert!(!log.as_array().unwrap().iter().any(|t| t.as_str().unwrap().contains("Le gateway a démarré")),
            "only the plugin's records: {log}");
    });
}

#[test]
fn slayer_legends_switch_is_first_and_turns_the_plugin_off_in_the_gateway() {
    let cp = CloudPhone::start_with(json!({"plugins": [SLAYER_LEGEND]}));
    let phone = cp.clone();
    browser_test(&cp, Options::without_video(), |page| async move {
        page.open_options().await;
        page.wait_js("the plugin's options", Duration::from_secs(15),
            "const d = document.querySelector('[role=dialog]'); return !!d && d.innerText.includes('Mode et farming')", vec![]).await;
        let lines = page.dialog_lines(O).await;
        let at = lines.iter().position(|l| l == "Slayer Legend").unwrap_or_else(|| panic!("{lines:#?}"));
        assert_eq!(lines.get(at + 1).map(String::as_str), Some("Plugin"), "the switch first: {lines:#?}");
        assert_eq!(page.control_state(&page.control(O, "Plugin").await).await["value"], "on", "on by default");
        page.control(O, "Plugin").await.select_by_value("off").await.unwrap();
        let p = phone.clone();
        blocking(move || wait_for("the plugin off", Duration::from_secs(10), || {
            (p.try_get_json("api/v1/plugins/slayer-legend/enabled")?["enabled"] == json!(false)).then_some(())
        }));
        // The watchdog no longer looks, and État says so.
        let p = phone.clone();
        blocking(move || wait_for("the watchdog off", Duration::from_secs(40), || {
            (p.try_get_json("api/v1/plugins/slayer-legend/watchdog")?["status"]["template"] == "Plugin désactivé").then_some(())
        }));
        page.wait_dialog_value(O, "État", Duration::from_secs(25), |v| v.ends_with(" · Plugin désactivé")).await;
        // A browser with no settings of its own shows the gateway's state.
        page.js("localStorage.clear(); return true", vec![]).await;
        page.reload(false).await;
        page.open_options().await;
        page.wait_js("the switch off", Duration::from_secs(15),
            "const l = [...document.querySelectorAll('[role=dialog] label')].find(l => l.innerText.trim().startsWith('Plugin')); \
             return !!l && l.control.value === 'off'", vec![]).await;
    });
}

#[test]
fn slayer_legends_switch_on_hold_shows_in_the_state_row_with_free_play_and_resume() {
    // The game in front: an input there is playing (on the launcher it is not).
    let app = json!({"package": "com.gear2.growslayer", "activity": "com.google.firebase.MessagingUnityPlayerActivity",
        "state": "running", "picture": [[0.36, 0.012, 0.42, 0.036, [40, 200, 60]], [0.0, 0.972, 1.0, 0.998, [225, 225, 225]]]});
    let cp = CloudPhone::start_with(json!({"plugins": [SLAYER_LEGEND], "options": {"app": app}}));
    let mode = "api/v1/plugins/slayer-legend/mode";
    // The user plays: the switch to mpw4 is on hold.
    assert_eq!(cp.post_json("api/v1/input", &json!({})).status(), 200);
    assert_eq!(cp.post_json(mode, &json!({"mode": "mpw4", "stage4": 31})).status(), 200);
    wait_for("the switch on hold", Duration::from_secs(20), || {
        (!cp.try_get_json(mode)?["hold"].is_null()).then_some(())
    });
    let phone = cp.clone();
    browser_test(&cp, Options::without_video(), |page| async move {
        page.open_options().await;
        let state = page.wait_dialog_value(O, "État", Duration::from_secs(20),
            |v| v.contains(" · en attente : tu joues · nouvel essai dans ")).await;
        assert!(state.starts_with("Farming mpw4 · en attente : tu joues · nouvel essai dans "), "{state}");
        assert!(state.ends_with(" s Jeu libre Reprendre"), "both buttons inline: {state}");
        page.client.find(Locator::XPath(
            "//div[@role='dialog']//div[span[normalize-space()='État']]//button[normalize-space()='Jeu libre']"))
            .await.unwrap().click().await.unwrap();
        let p = phone.clone();
        let answer = blocking(move || wait_for("free play", Duration::from_secs(10), || {
            let answer = p.try_get_json("api/v1/plugins/slayer-legend/mode")?;
            (answer["mode"] == "free").then_some(answer)
        }));
        assert_eq!(answer["hold"], serde_json::Value::Null, "{answer}");
        // The page follows: no more buttons, the radio on free play.
        page.wait_dialog_value(O, "État", Duration::from_secs(20), |v| v.starts_with("Jeu libre")).await;
        let start = std::time::Instant::now();
        while page.stored_settings().await["plugins"]["slayer-legend"]["mode"] != "free" {
            assert!(start.elapsed() < Duration::from_secs(15), "the radio follows free play");
            tokio::time::sleep(Duration::from_millis(300)).await;
        }
    });
}
