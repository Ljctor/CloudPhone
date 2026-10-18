//! The information panel's server tab: the fields that restart Android: renderer, cores, memory
//! ("Réglages d’Android") and the screen's shape and resolution ("Appareil",
//! "Résolution"). They are found by their labels and each one's "Appliquer"
//! is the one that follows it, so the tests hold whether the panel shows one
//! form or two. They only change fields here; pressing "Appliquer" is in
//! ui_changes.rs.
use cloudphone_e2e::browser::{browser_test, fr, Options, Page};
use cloudphone_e2e::*;
use serde_json::Value;
use std::time::Duration;

const P: &str = fr::INFO_PANEL;

pub async fn open_server_panel(page: &Page) {
    page.open_info(fr::SERVER_TAB).await;
    // The forms fill in from the API.
    page.wait_js(
        "the Android settings form",
        Duration::from_secs(15),
        "const d = document.querySelector('[role=dialog]'); return d && d.querySelectorAll('select').length >= 5",
        vec![],
    )
    .await;
}

/// Whether the "Appliquer" serving the labelled field is disabled.
async fn apply_disabled(page: &Page, label: &str) -> bool {
    let control = page.control(P, label).await;
    page.apply_disabled_for(&control).await
}

/// The sizes the screen form shows (the running or the chosen one).
async fn shown_sizes(page: &Page) -> Vec<(u64, u64)> {
    let control = page.control(P, "Résolution").await;
    browser::sizes_in(&page.section_text_for(&control).await)
}

async fn value(page: &Page, label: &str) -> String {
    let control = page.control(P, label).await;
    page.control_state(&control).await["value"].as_str().unwrap().to_string()
}

async fn options(page: &Page, label: &str) -> Vec<String> {
    let control = page.control(P, label).await;
    browser::strings(&page.control_state(&control).await["options"])
}

use cloudphone_e2e::browser;

fn values(options: &[String]) -> Vec<String> {
    options.iter().map(|o| o.split(':').next().unwrap().to_string()).collect()
}

#[test]
fn the_android_settings_form_shows_what_android_runs_with() {
    let cp = CloudPhone::start();
    let settings = cp.get_json("api/v1/emulator-settings");
    browser_test(&cp, Options::without_video(), |page| async move {
        open_server_panel(&page).await;
        let current = &settings["current"];
        assert_eq!(value(&page, "Moteur de rendu").await, current["renderer"].as_str().unwrap());
        assert_eq!(value(&page, "Cœurs").await, current["cores"].as_str().unwrap());
        assert_eq!(value(&page, "Mémoire").await, current["memoryMb"].as_str().unwrap());
        assert!(apply_disabled(&page, "Cœurs").await, "Apply is disabled while nothing changed");
    });
}

#[test]
fn the_android_settings_choices_follow_the_servers_limits() {
    let cp = CloudPhone::start();
    let settings = cp.get_json("api/v1/emulator-settings");
    browser_test(&cp, Options::without_video(), |page| async move {
        open_server_panel(&page).await;
        let limits = &settings["limits"];
        let renderers: Vec<String> = limits["renderers"].as_array().unwrap().iter().map(|v| v.as_str().unwrap().to_string()).collect();
        assert_eq!(values(&options(&page, "Moteur de rendu").await), renderers);
        let max_cores = limits["maxCores"].as_u64().unwrap();
        for cores in values(&options(&page, "Cœurs").await) {
            let n: u64 = cores.parse().unwrap();
            assert!(n >= 1 && n <= max_cores.max(settings["current"]["cores"].as_str().unwrap().parse().unwrap()), "cores {n} within limits");
        }
        let max_memory = limits["maxMemoryMb"].as_u64().unwrap();
        let memory = values(&options(&page, "Mémoire").await);
        assert!(!memory.is_empty());
        for mb in memory {
            let n: u64 = mb.parse().unwrap();
            assert!(n >= 2048 && n <= max_memory && n % 1024 == 0, "memory {n} MB within 2 GB..{max_memory} MB, whole GB");
        }
        let labels = options(&page, "Moteur de rendu").await;
        assert!(labels.iter().any(|o| o == "lavapipe:Lavapipe (recommandé)"), "{labels:?}");
    });
}

#[test]
fn apply_settings_is_enabled_only_while_the_form_differs() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    let settings = cp.get_json("api/v1/emulator-settings");
    browser_test(&cp, Options::without_video(), |page| async move {
        open_server_panel(&page).await;
        let current_cores = settings["current"]["cores"].as_str().unwrap().to_string();
        let other = values(&options(&page, "Cœurs").await).into_iter().find(|c| *c != current_cores).expect("another core count");
        page.control(P, "Cœurs").await.select_by_value(&other).await.unwrap();
        assert!(!apply_disabled(&page, "Cœurs").await, "a change enables Apply");
        page.control(P, "Cœurs").await.select_by_value(&current_cores).await.unwrap();
        assert!(apply_disabled(&page, "Cœurs").await, "back to the running value disables it");

        let current_memory = settings["current"]["memoryMb"].as_str().unwrap().to_string();
        let other = values(&options(&page, "Mémoire").await).into_iter().find(|m| *m != current_memory).unwrap();
        page.control(P, "Mémoire").await.select_by_value(&other).await.unwrap();
        assert!(!apply_disabled(&page, "Mémoire").await);
        page.control(P, "Mémoire").await.select_by_value(&current_memory).await.unwrap();
        assert!(apply_disabled(&page, "Mémoire").await);
        // Nothing was requested.
        let request = phone.get_json("api/v1/emulator-settings")["request"]["state"].clone();
        assert_eq!(request, "idle", "no change was sent to the server");
        assert_eq!(phone.fake().record()["requests"]["settings"], serde_json::json!([]), "nothing reached the root service");
    });
}

#[test]
fn the_renderer_hint_follows_the_choice() {
    let cp = CloudPhone::start();
    let settings = cp.get_json("api/v1/emulator-settings");
    browser_test(&cp, Options::without_video(), |page| async move {
        open_server_panel(&page).await;
        let hints = [
            ("lavapipe", "Couleurs justes, le plus rapide sans carte graphique."),
            ("swiftshader", "Rapide, mais certaines couleurs du jeu peuvent être fausses."),
            ("swangle", "Couleurs justes, mais lent et très gourmand."),
            ("software", "Rendu logiciel par défaut de l’émulateur."),
        ];
        let offered = values(&options(&page, "Moteur de rendu").await);
        for (renderer, hint) in hints.iter().filter(|(r, _)| offered.iter().any(|o| o == r)) {
            page.control(P, "Moteur de rendu").await.select_by_value(renderer).await.unwrap();
            let text = page.dialog_text(P).await;
            assert!(text.contains(hint), "{renderer}: hint {hint:?} shown");
        }
        let current = settings["current"]["renderer"].as_str().unwrap();
        page.control(P, "Moteur de rendu").await.select_by_value(current).await.unwrap();
        assert!(apply_disabled(&page, "Moteur de rendu").await);
    });
}

#[test]
fn the_screen_form_shows_the_running_size() {
    let cp = CloudPhone::start();
    let display = cp.get_json("api/v1/display");
    browser_test(&cp, Options::without_video(), |page| async move {
        open_server_panel(&page).await;
        let size = format!("{}×{}", display["configured"]["width"], display["configured"]["height"]);
        let w = display["configured"]["width"].as_u64().unwrap();
        let h = display["configured"]["height"].as_u64().unwrap();
        let shown = shown_sizes(&page).await;
        assert!(shown.contains(&(w, h)), "the screen form shows {size}: {shown:?}");
        assert!(apply_disabled(&page, "Résolution").await, "Apply is disabled while nothing changed");
        let devices = values(&options(&page, "Appareil").await);
        for device in ["s23", "pixel", "classic", "tablet", "fold", "window"] {
            assert!(devices.iter().any(|d| d == device), "device preset {device} in {devices:?}");
        }
        let resolutions = values(&options(&page, "Résolution").await);
        assert_eq!(resolutions, ["360", "480", "720", "1080"]);
        let labels = options(&page, "Résolution").await;
        assert!(labels.iter().any(|o| o == "480:480p (défaut)"), "480p is the default: {labels:?}");
    });
}

#[test]
fn apply_screen_size_is_enabled_only_while_the_size_differs() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    let display = cp.get_json("api/v1/display");
    browser_test(&cp, Options::without_video(), |page| async move {
        open_server_panel(&page).await;
        let resolution = value(&page, "Résolution").await;
        let other = if resolution == "720" { "360" } else { "720" };
        page.control(P, "Résolution").await.select_by_value(other).await.unwrap();
        let width: u64 = other.parse().unwrap();
        let shown = shown_sizes(&page).await;
        assert!(shown.iter().any(|&(w, _)| w == width), "the preview shows the new width {width}: {shown:?}");
        assert!(!apply_disabled(&page, "Résolution").await, "a different size enables Apply");
        page.control(P, "Résolution").await.select_by_value(&resolution).await.unwrap();
        assert!(apply_disabled(&page, "Résolution").await, "back to the running size disables it");
        let state: Value = phone.get_json("api/v1/display");
        assert_eq!(state["request"], display["request"], "no size change was sent");
    });
}

#[test]
fn every_screen_preset_gives_an_even_size_within_the_limits() {
    let cp = CloudPhone::start();
    let display = cp.get_json("api/v1/display");
    browser_test(&cp, Options::without_video(), |page| async move {
        open_server_panel(&page).await;
        let limits = display["limits"].clone();
        let (device0, resolution0) = (value(&page, "Appareil").await, value(&page, "Résolution").await);
        for device in values(&options(&page, "Appareil").await) {
            page.control(P, "Appareil").await.select_by_value(&device).await.unwrap();
            for resolution in ["360", "480", "720", "1080"] {
                page.control(P, "Résolution").await.select_by_value(resolution).await.unwrap();
                let shown = shown_sizes(&page).await;
                let &(w, h) = shown.last().unwrap_or_else(|| panic!("{device} {resolution}: no size shown"));
                assert!(w % 2 == 0 && h % 2 == 0, "{device} {resolution}: even size {w}×{h}");
                assert!(w >= limits["width"][0].as_u64().unwrap() && w <= limits["width"][1].as_u64().unwrap(), "{device} {resolution}: width {w}");
                assert!(h >= limits["height"][0].as_u64().unwrap() && h <= limits["height"][1].as_u64().unwrap(), "{device} {resolution}: height {h}");
            }
        }
        page.control(P, "Appareil").await.select_by_value(&device0).await.unwrap();
        page.control(P, "Résolution").await.select_by_value(&resolution0).await.unwrap();
        assert!(apply_disabled(&page, "Résolution").await, "form restored to the running size");
    });
}
