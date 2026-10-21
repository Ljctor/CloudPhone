//! The two panels: "Informations" (the ping and fps block; tabs Client and
//! Serveur) and "Options" (the cog: language, page options, plugins).
use cloudphone_e2e::browser::{browser_test, fr, Options, Page};
use cloudphone_e2e::*;
use serde_json::json;
use std::time::Duration;

const SECTIONS_SERVER: [&str; 5] = ["État", "Machine", "Android", "Flux envoyé", "Réglages d’Android"];
const SECTIONS_CLIENT: [&str; 3] = ["Réseau", "Affichage", "Entrées"];
const P: &str = fr::INFO_PANEL;

async fn open_server_panel(page: &Page) {
    page.open_info(fr::SERVER_TAB).await;
}

async fn open_client_panel(page: &Page) {
    page.open_info(fr::CLIENT_TAB).await;
}

async fn expanded(page: &Page, label: &str) -> Option<String> {
    page.by_label(label).await.attr("aria-expanded").await.unwrap()
}

fn assert_in_order(lines: &[String], wanted: &[&str], panel: &str) {
    let mut from = 0;
    for heading in wanted {
        let at = lines[from..].iter().position(|l| l == heading).map(|i| i + from);
        let at = at.unwrap_or_else(|| panic!("{panel}: section {heading:?} missing or out of order in {lines:#?}"));
        from = at + 1;
    }
}

#[test]
fn the_metrics_block_opens_the_information_panel_on_its_client_tab() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        assert_eq!(expanded(&page, fr::INFO).await.as_deref(), Some("false"));
        page.click_label(fr::INFO).await;
        page.wait_dialog(P).await;
        assert_eq!(expanded(&page, fr::INFO).await.as_deref(), Some("true"));
        assert_eq!(page.open_dialogs().await, [P]);
        let tabs = page.js("return [...document.querySelectorAll('[role=dialog] [role=tab]')].map(t => [t.innerText.trim(), t.getAttribute('aria-selected')])", vec![]).await;
        assert_eq!(tabs, json!([["Client", "true"], ["Serveur", "false"]]), "two tabs, Client first and selected");
        let lines = page.dialog_lines(P).await;
        assert_eq!(lines.first().map(String::as_str), Some(P), "the panel shows its title");
        assert_in_order(&lines, &SECTIONS_CLIENT, P);
        assert!(!lines.iter().any(|l| l == "Machine"), "the server's sections are on the other tab: {lines:#?}");
    });
}

#[test]
fn the_server_tab_shows_the_server_sections_and_android_settings() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        open_server_panel(&page).await;
        assert_eq!(page.open_dialogs().await, [P]);
        let lines = page.dialog_lines(P).await;
        assert_in_order(&lines, &SECTIONS_SERVER, P);
        for field in ["Moteur de rendu", "Cœurs", "Appareil", "Résolution", "Appliquer"] {
            assert!(lines.iter().any(|l| l == field), "field {field:?} in {lines:#?}");
        }
    });
}

#[test]
fn the_server_panel_fills_in_values_that_agree_with_the_server() {
    let cp = CloudPhone::start();
    let (state, display, settings) = (cp.get_json("api/v1/state"), cp.get_json("api/v1/display"), cp.get_json("api/v1/emulator-settings"));
    browser_test(&cp, Options::default(), |page| async move {
        open_server_panel(&page).await;
        let p = P;
        let long = Duration::from_secs(20);
        page.wait_dialog_value(p, "Serveur", long, |v| v == "joignable").await;
        let unit = format!("{} ({})", state["emulator"]["active"].as_str().unwrap(), state["emulator"]["sub"].as_str().unwrap());
        page.wait_dialog_value(p, "Service Android", long, |v| v.starts_with(&unit)).await;
        page.wait_dialog_value(p, "Android démarré", long, |v| v == "oui").await;
        page.wait_dialog_value(p, "Appareils connectés", long, |v| v.parse::<u64>().map(|n| n >= 1).unwrap_or(false)).await;
        let cpus = state["load"]["cpus"].as_u64().unwrap();
        page.wait_dialog_value(p, "Charge du serveur", long, |v| v.contains(&format!("pour {cpus} threads"))).await;
        page.wait_dialog_value(p, "Processeur", long, |v| v.ends_with(&format!("% de {cpus} threads"))).await;
        page.wait_dialog_value(p, "Mémoire", long, |v| v.contains("utilisés /")).await;
        let size = format!("{}×{} px", display["running"]["width"], display["running"]["height"]);
        page.wait_dialog_value(p, "Écran Android", long, |v| v == size).await;
        let current = &settings["current"];
        let renderer = current["renderer"].as_str().unwrap().to_string();
        page.wait_dialog_value(p, "Moteur de rendu", long, |v| v == renderer).await;
        let cores = format!("{} cœurs", current["cores"].as_str().unwrap());
        page.wait_dialog_value(p, "Cœurs et mémoire", long, |v| v.starts_with(&cores)).await;
        page.wait_dialog_value(p, "Codec", long, |v| ["VP8", "VP9", "H264"].contains(&v)).await;
        page.wait_dialog_value(p, "Flux vidéo", long, |v| v.contains(" px")).await;
        page.wait_dialog_value(p, "Débit vidéo", long, |v| v.ends_with("kbit/s")).await;
        page.wait_dialog_value(p, "Images envoyées", long, |v| v.ends_with("/s")).await;
    });
}

#[test]
fn the_information_panel_closes_with_its_cross_and_with_its_block() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        open_server_panel(&page).await;
        let cross = page
            .js("return document.querySelector('[role=dialog] [aria-label=\"Fermer\"]') !== null", vec![])
            .await;
        assert_eq!(cross, json!(true), "the panel has a cross labelled Fermer");
        let close = page.client.find(fantoccini::Locator::Css("[role=dialog] [aria-label=\"Fermer\"]")).await.unwrap();
        close.click().await.unwrap();
        page.wait_no_dialog().await;
        assert_eq!(expanded(&page, fr::INFO).await.as_deref(), Some("false"));
        // The block toggles it too.
        open_server_panel(&page).await;
        page.click_label(fr::INFO).await;
        page.wait_no_dialog().await;
    });
}

#[test]
fn the_cog_opens_the_options_panel_with_the_page_options_and_plugins() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        assert_eq!(expanded(&page, fr::OPTIONS).await.as_deref(), Some("false"));
        page.open_options().await;
        assert_eq!(expanded(&page, fr::OPTIONS).await.as_deref(), Some("true"));
        let lines = page.dialog_lines(fr::OPTIONS_PANEL).await;
        assert_eq!(lines.first().map(String::as_str), Some(fr::OPTIONS_PANEL));
        assert_in_order(&lines, &["Langue", "Afficher le curseur", "Replier la barre 3 s après l’entrée en plein écran", "Plugins", "Aucun plugin installé."], fr::OPTIONS_PANEL);
        page.click_label(fr::OPTIONS).await;
        page.wait_no_dialog().await;
    });
}

#[test]
fn the_client_panel_describes_this_browser_and_its_stream() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::default(), |page| async move {
        open_client_panel(&page).await;
        let p = P;
        let long = Duration::from_secs(20);
        page.wait_dialog_value(p, "Connexion", long, |v| v == "connected").await;
        page.wait_dialog_value(p, "Ping", long, |v| v.contains("ms")).await;
        page.wait_dialog_value(p, "Images affichées", long, |v| v.ends_with("/s")).await;
        let window = page.js("return innerWidth + '×' + innerHeight", vec![]).await;
        let window = window.as_str().unwrap().to_string();
        page.wait_dialog_value(p, "Fenêtre", long, |v| v.starts_with(&format!("{window} CSS"))).await;
        let video = page.video().await;
        let shown = format!("{}×{} CSS", video["cssW"].as_f64().unwrap().round(), video["cssH"].as_f64().unwrap().round());
        page.wait_dialog_value(p, "Image affichée", long, |v| v.starts_with(&shown)).await;
        let dpr = page.js("return devicePixelRatio", vec![]).await.as_f64().unwrap();
        page.wait_dialog_value(p, "Densité", long, |v| v == format!("×{dpr:.2}")).await;
        // No touch sent yet.
        assert_eq!(page.dialog_value(p, "Touches via").await.as_deref(), Some("–"));
    });
}

#[test]
fn only_one_panel_is_open_at_a_time() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        open_server_panel(&page).await;
        page.open_options().await;
        assert_eq!(page.open_dialogs().await, [fr::OPTIONS_PANEL]);
        assert_eq!(expanded(&page, fr::INFO).await.as_deref(), Some("false"));
        page.click_label(fr::INFO).await;
        page.wait_dialog(P).await;
        assert_eq!(page.open_dialogs().await, [P]);
        assert_eq!(expanded(&page, fr::OPTIONS).await.as_deref(), Some("false"));
    });
}

#[test]
fn the_information_panel_always_opens_on_the_client_tab() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        open_server_panel(&page).await;
        page.click_label(fr::INFO).await;
        page.wait_no_dialog().await;
        page.click_label(fr::INFO).await;
        page.wait_dialog(P).await;
        let selected = page.js("const t = document.querySelector('[role=dialog] [role=tab][aria-selected=true]'); return t && t.innerText.trim()", vec![]).await;
        assert_eq!(selected, json!("Client"), "closed on the server tab, reopened on the client tab");
    });
}

#[test]
fn the_disconnect_button_is_offered_when_another_device_watches() {
    let cp = CloudPhone::start();
    // One more viewer for the length of the test, so there is always another device.
    let other = Viewer::open(&cp, &viewer_id("other"));
    browser_test(&cp, Options::default(), |page| async move {
        open_server_panel(&page).await;
        let value = page.wait_dialog_value(P, "Autres appareils", Duration::from_secs(20), |v| v == "Déconnecter").await;
        assert_eq!(value, "Déconnecter");
        assert_eq!(page.dialog_buttons(P, "Déconnecter").await, [false], "an enabled Disconnect button (never clicked here)");
        let count: u64 = page.dialog_value(P, "Appareils connectés").await.unwrap().parse().unwrap();
        assert!(count >= 2, "this page and the extra viewer are counted: {count}");
    });
    other.close();
}

#[test]
fn panel_values_keep_updating_while_open() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::default(), |page| async move {
        open_client_panel(&page).await;
        page.wait_dialog_value(P, "Tampon vidéo", Duration::from_secs(20), |v| v.ends_with("ms")).await;
        let first = page.dialog_text(P).await;
        let start = std::time::Instant::now();
        let mut last = first.clone();
        while start.elapsed() < Duration::from_secs(20) && last == first {
            page.sleep(Duration::from_millis(500)).await;
            last = page.dialog_text(P).await;
        }
        assert_ne!(last, first, "the panel's live values (ping, frames, buffer) refresh within 20 s");
    });
}

#[test]
fn the_phone_alerts_give_a_copy_button_for_the_ntfy_link_without_showing_it() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::without_video(), |page| async move {
        page.open_options().await;
        let o = fr::OPTIONS_PANEL;
        page.wait_js("the alerts' switch", Duration::from_secs(10),
            "const d = document.querySelector('[role=dialog]'); return !!d && d.innerText.includes('Alertes par ntfy')", vec![]).await;
        page.control(o, "Alertes par ntfy").await.click().await.unwrap();
        page.wait_js("the topic's row", Duration::from_secs(10),
            "const d = document.querySelector('[role=dialog]'); return !!d && d.innerText.includes('Lien topic ntfy')", vec![]).await;
        let text = page.dialog_text(o).await;
        assert!(!text.contains("ntfy.sh/"), "the link is not shown: {text}");
        assert!(text.contains("ntfy est une app de notifications (Android, iOS, web). Installe-la, touche + et colle le lien."), "{text}");
        let copy = page.js("return [...document.querySelectorAll('[role=dialog] button')].some(b => b.getAttribute('aria-label') === 'Copier le lien')",
            vec![]).await;
        assert_eq!(copy, json!(true), "{text}");
    });
}
