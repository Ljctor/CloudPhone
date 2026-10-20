//! Input from the page reaching Android, read back from what the fake
//! emulator received: a click lands on the Android pixel under the pointer,
//! toolbar keys arrive as the emulator's key names, over the stream's data
//! channels or, without them, over HTTP. Touches and keys on the real phone
//! are in `smoke.rs`.
use cloudphone_e2e::browser::{blocking, browser_test, fr, Options, Page};
use cloudphone_e2e::*;
use serde_json::{json, Value};
use std::time::Duration;

const SOON: Duration = Duration::from_secs(10);

/// The surface's CSS pixels per Android pixel, both ways: the error a
/// WebDriver pointer (whole CSS pixels) may add to a touch's coordinates.
async fn tolerance(page: &Page, display: (u64, u64)) -> f64 {
    let rect = page.rect(&cloudphone_e2e::browser::css_label(fr::TOUCH_SURFACE)).await;
    let scale = (display.0 as f64 / rect["w"].as_f64().unwrap()).max(display.1 as f64 / rect["h"].as_f64().unwrap());
    scale.ceil() + 1.0
}

/// Clicks Android's pixel (x, y) and gives the touches the click produced.
async fn click_android(page: &Page, phone: &CloudPhone, display: (u64, u64), x: u64, y: u64) -> Vec<Value> {
    let before = phone.fake().touches().len();
    let (vx, vy) = page.viewport_point(display, x, y).await;
    page.click_at(vx, vy).await;
    let fake = phone.clone();
    blocking(move || {
        fake.fake().wait_record("the click's press and release", SOON, |record| {
            let touches = record["touches"].as_array()?;
            let new = &touches[before.min(touches.len())..];
            (new.iter().any(|t| t["pressure"] == 0) && new.len() >= 2).then(|| new.to_vec())
        })
    })
}

fn near(touch: &Value, x: u64, y: u64, tolerance: f64) -> bool {
    (touch["x"].as_f64().unwrap() - x as f64).abs() <= tolerance && (touch["y"].as_f64().unwrap() - y as f64).abs() <= tolerance
}

async fn clicks_land_under_the_pointer(phone: CloudPhone, page: Page, display: (u64, u64), via: &str) {
    let tolerance = tolerance(&page, display).await;
    let (w, h) = display;
    for (x, y) in [(w / 2, h / 2), (w / 5, h / 6), (w * 4 / 5, h * 5 / 6), (10, h - 10), (w - 10, 10)] {
        let touches = click_android(&page, &phone, display, x, y).await;
        let (down, up) = (&touches[0], touches.last().unwrap());
        assert!(near(down, x, y, tolerance), "click on Android ({x}, {y}) of {w}x{h} arrives at ({}, {}) ± {tolerance}: {touches:?}", down["x"], down["y"]);
        assert!(near(up, x, y, tolerance), "release at the same place: {up}");
        assert_eq!(down["pressure"], 1024, "a press: {down}");
        assert_eq!(up["pressure"], 0, "then a release: {up}");
        for t in &touches {
            assert_eq!(t["identifier"], 0, "one finger: {t}");
            assert_eq!(t["display"], 0, "the main display: {t}");
            assert_eq!(t["via"], via, "the path: {t}");
            assert!(t["x"].as_u64().unwrap() < w && t["y"].as_u64().unwrap() < h, "inside the screen: {t}");
        }
        assert_eq!(down["touch_major"], 8);
        assert_eq!(up["touch_major"], 0);
    }
}

#[test]
fn a_click_lands_on_the_android_pixel_under_the_pointer() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        clicks_land_under_the_pointer(phone, page, (480, 1040), "touch").await;
    });
}

#[test]
fn clicks_land_right_on_a_screen_of_another_size() {
    // A bigger and wider screen than the page's default: the mapping must
    // follow the size the gateway reports.
    let cp = CloudPhone::start_with(json!({"display": {"width": 720, "height": 1152, "density": 320}}));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        clicks_land_under_the_pointer(phone, page, (720, 1152), "touch").await;
    });
}

#[test]
fn clicks_land_right_in_a_window_of_another_shape() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    let options = Options { window: (1000, 700), ..Options::default() };
    browser_test(&cp, options, |page| async move {
        clicks_land_under_the_pointer(phone, page, (480, 1040), "touch").await;
    });
}

#[test]
fn without_data_channels_touches_go_over_http_to_the_same_place() {
    let cp = CloudPhone::start_with(json!({"options": {"data_channels": false}}));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        clicks_land_under_the_pointer(phone, page, (480, 1040), "grpc").await;
    });
}

#[test]
fn a_drag_sends_moves_in_order_then_one_release() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        let from = page.viewport_point((480, 1040), 240, 300).await;
        let to = page.viewport_point((480, 1040), 240, 800).await;
        let surface = page.by_label(fr::TOUCH_SURFACE).await;
        let _ = surface;
        // A mouse drag (press, moves, release).
        let client = &page.client;
        use fantoccini::actions::{InputSource, MouseActions, PointerAction, MOUSE_BUTTON_LEFT};
        let mut mouse = MouseActions::new("mouse".into())
            .then(PointerAction::MoveTo { duration: None, x: from.0, y: from.1 })
            .then(PointerAction::Down { button: MOUSE_BUTTON_LEFT });
        for i in 1..=10 {
            let f = i as f64 / 10.0;
            mouse = mouse.then(PointerAction::MoveTo { duration: Some(Duration::from_millis(40)), x: from.0, y: from.1 + (to.1 - from.1) * f });
        }
        mouse = mouse.then(PointerAction::Up { button: MOUSE_BUTTON_LEFT });
        client.perform_actions(mouse).await.expect("drag");
        let _ = client.release_actions().await;
        let fake = phone.clone();
        let touches = blocking(move || {
            fake.fake().wait_record("the drag's release", SOON, |r| {
                let t = r["touches"].as_array()?;
                (t.last()?["pressure"] == 0).then(|| t.clone())
            })
        });
        assert!(touches.len() >= 4, "a press, some moves and a release: {touches:?}");
        let ys: Vec<u64> = touches.iter().map(|t| t["y"].as_u64().unwrap()).collect();
        assert!(ys.windows(2).all(|w| w[0] <= w[1]), "the finger only goes down: {ys:?}");
        assert!(touches[..touches.len() - 1].iter().all(|t| t["pressure"] == 1024), "pressed until the end: {touches:?}");
        assert_eq!(touches.iter().filter(|t| t["pressure"] == 0).count(), 1, "one release: {touches:?}");
        let tolerance = tolerance(&page, (480, 1040)).await;
        assert!(near(&touches[0], 240, 300, tolerance), "starts under the pointer: {}", touches[0]);
        assert!(near(touches.last().unwrap(), 240, 800, tolerance), "ends under the pointer: {}", touches.last().unwrap());
    });
}

const KEYS: [(&str, &str, &str); 6] = [
    (fr::BACK, "GoBack", "BACK"),
    (fr::HOME, "GoHome", "HOME"),
    (fr::RECENTS, "AppSwitch", "APP_SWITCH"),
    (fr::VOLUME_UP, "AudioVolumeUp", "VOLUME_UP"),
    (fr::VOLUME_DOWN, "AudioVolumeDown", "VOLUME_DOWN"),
    (fr::POWER, "Power", "POWER"),
];

#[test]
fn the_page_tells_the_gateway_of_inputs_at_once_then_every_5_s() {
    // Over the data channels the gateway sees no input: the page says so
    // with POST /api/v1/input, the first after a silence at once, then at
    // most one every 5 s. Read back through the probe plugin's last_input().
    let cp = CloudPhone::start_with(json!({"plugins": ["tests/fake-emulator/plugins/e2e-probe"]}));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        let probe = phone.clone();
        let last = move || probe.get_json("api/v1/plugins/e2e-probe/activity");
        let read = last.clone();
        let activity = blocking(move || read());
        assert_eq!(activity["last_input"], Value::Null, "{activity}");
        assert_eq!(activity["viewers"], 1, "this page: {activity}");
        let (x, y) = page.viewport_point((480, 1040), 240, 520).await;
        page.click_at(x, y).await;
        let read = last.clone();
        let first = blocking(move || {
            wait_for("the click's input", SOON, || {
                let input = read()["last_input"].clone();
                input["wall"].as_f64().map(|_| input)
            })
        });
        assert_eq!(phone.fake().touches().last().unwrap()["via"], "touch", "over the data channel");
        page.click_at(x, y).await;
        page.sleep(Duration::from_millis(1000)).await;
        let read = last.clone();
        assert_eq!(blocking(move || read())["last_input"], first, "within 5 s: not sent again");
        page.sleep(Duration::from_millis(4500)).await;
        page.click_label(fr::HOME).await;
        let (read, before) = (last.clone(), first.clone());
        let later = blocking(move || {
            wait_for("the key's input", SOON, || {
                let input = read()["last_input"].clone();
                (input != before).then_some(input)
            })
        });
        assert!(later["wall"].as_f64().unwrap() >= first["wall"].as_f64().unwrap() + 5.0, "{first} then {later}");
    });
}

#[test]
fn toolbar_keys_arrive_as_keypresses_on_the_keyboard_channel() {
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        for (label, key, _) in KEYS {
            let before = phone.fake().keys().len();
            page.click_label(label).await;
            let fake = phone.clone();
            let got = blocking(move || {
                fake.fake().wait_record(&format!("key {key}"), SOON, |r| {
                    let keys = r["keys"].as_array()?;
                    keys.get(before).cloned()
                })
            });
            assert_eq!(got["key"], key, "{label}: {got}");
            assert_eq!(got["via"], "keyboard", "{label} goes over the data channel: {got}");
            assert_eq!(got["eventType"], 2, "{label} is one keypress (down and up): {got}");
        }
        page.sleep(Duration::from_millis(500)).await;
        assert_eq!(phone.fake().keys().len(), KEYS.len(), "one key per click: {:?}", phone.fake().keys());
    });
}

#[test]
fn without_data_channels_toolbar_keys_go_through_adb() {
    let cp = CloudPhone::start_with(json!({"options": {"data_channels": false}}));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        for (label, key, keycode) in KEYS {
            let before = phone.fake().keys().len();
            page.click_label(label).await;
            let fake = phone.clone();
            let got = blocking(move || {
                fake.fake().wait_record(&format!("key {key} through adb"), SOON, |r| r["keys"].as_array()?.get(before).cloned())
            });
            assert_eq!(got["key"], keycode, "{label}: {got}");
            assert_eq!(got["via"], "adb", "{label}: {got}");
        }
        let adb = phone.fake().record()["adb"].clone();
        assert!(adb.as_array().unwrap().iter().any(|l| l.as_str().unwrap().contains("-s emulator-5558 shell input keyevent BACK")), "adb call names the device: {adb}");
    });
}

#[test]
fn the_client_panel_says_which_path_touches_took() {
    for (channels, path) in [(true, "data channel"), (false, "HTTP")] {
        let cp = CloudPhone::start_with(json!({"options": {"data_channels": channels}}));
        let phone = cp.clone();
        browser_test(&cp, Options::default(), |page| async move {
            click_android(&page, &phone, (480, 1040), 240, 520).await;
            page.open_info(fr::CLIENT_TAB).await;
            assert_eq!(page.dialog_value(fr::INFO_PANEL, "Touches via").await.as_deref(), Some(path));
        });
    }
}

#[test]
fn the_page_never_writes_to_the_input_channel() {
    // Emulator 36.6.11 ignores the driver's own "input" channel: everything
    // must go to "touch" and "keyboard".
    let cp = CloudPhone::start();
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        click_android(&page, &phone, (480, 1040), 100, 100).await;
        page.click_label(fr::HOME).await;
        let fake = phone.clone();
        blocking(move || fake.fake().wait_record("the key", SOON, |r| (!r["keys"].as_array()?.is_empty()).then_some(())));
        let messages = phone.fake().record()["channel_messages"].clone();
        let labels: Vec<&str> = messages.as_array().unwrap().iter().map(|m| m["label"].as_str().unwrap()).collect();
        assert!(!labels.is_empty(), "the page used the data channels");
        assert!(labels.iter().all(|l| *l == "touch" || *l == "keyboard"), "only touch and keyboard: {labels:?}");
        assert!(messages.as_array().unwrap().iter().all(|m| m["binary"] == true && m.get("error").is_none()), "raw protobuf: {messages}");
    });
}

#[test]
fn a_held_finger_shows_in_the_video_android_sends_back() {
    // The fake draws a white disc where Android feels a finger: the round
    // trip page → Android → video.
    let cp = CloudPhone::start_with(json!({}));
    let phone = cp.clone();
    browser_test(&cp, Options::default(), |page| async move {
        // Below the moving bar (middle three fifths), away from the texts.
        let (x, y) = (360u64, 920u64);
        let area = (x as f64 / 480.0 - 0.05, y as f64 / 1040.0 - 0.025, x as f64 / 480.0 + 0.05, y as f64 / 1040.0 + 0.025);
        let control = (0.05, 0.86, 0.25, 0.91);
        page.sleep(Duration::from_secs(1)).await;
        let base = page.frame(96).await;
        let (vx, vy) = page.viewport_point((480, 1040), x, y).await;
        page.press_at(vx, vy).await;
        let fake = phone.clone();
        blocking(move || fake.fake().wait_record("the press", SOON, |r| r["touches"].as_array()?.first().cloned()));
        let mut shown = 0.0;
        for _ in 0..20 {
            page.sleep(Duration::from_millis(200)).await;
            shown = page.frame(96).await.changed(&base, area, 40);
            if shown > 0.15 {
                break;
            }
        }
        let elsewhere = page.frame(96).await.changed(&base, control, 40);
        page.release().await;
        assert!(shown > 0.15, "the disc appears under the finger: {shown:.2} of the area changed");
        assert!(elsewhere < 0.05, "and nowhere else: {elsewhere:.2}");
    });
}

#[test]
fn a_drag_past_the_screen_edge_ends_on_the_edge() {
    // A wide window: room right of the screen for the pointer to leave it.
    let cp = CloudPhone::start();
    let phone = cp.clone();
    let options = Options { window: (700, 960), ..Options::default() };
    browser_test(&cp, options, |page| async move {
        let rect = page.rect(&cloudphone_e2e::browser::css_label(fr::TOUCH_SURFACE)).await;
        let right = rect["x"].as_f64().unwrap() + rect["w"].as_f64().unwrap();
        let width = page.js("return window.innerWidth", vec![]).await.as_f64().unwrap();
        assert!(width - right > 30.0, "room right of the screen: {rect} in {width} px");
        let from = page.viewport_point((480, 1040), 400, 520).await;
        let to = (right + 25.0, from.1);
        let client = &page.client;
        use fantoccini::actions::{InputSource, MouseActions, PointerAction, MOUSE_BUTTON_LEFT};
        let mut mouse = MouseActions::new("mouse".into())
            .then(PointerAction::MoveTo { duration: None, x: from.0, y: from.1 })
            .then(PointerAction::Down { button: MOUSE_BUTTON_LEFT });
        for i in 1..=8 {
            let f = i as f64 / 8.0;
            mouse = mouse.then(PointerAction::MoveTo { duration: Some(Duration::from_millis(40)), x: from.0 + (to.0 - from.0) * f, y: from.1 });
        }
        mouse = mouse.then(PointerAction::Up { button: MOUSE_BUTTON_LEFT });
        client.perform_actions(mouse).await.expect("drag");
        let _ = client.release_actions().await;
        let fake = phone.clone();
        let touches = blocking(move || {
            fake.fake().wait_record("the drag's release", SOON, |r| {
                let t = r["touches"].as_array()?;
                (t.last()?["pressure"] == 0).then(|| t.clone())
            })
        });
        assert!(touches.iter().all(|t| t["x"].as_u64().unwrap() <= 479), "never past Android's right edge: {touches:?}");
        let last = touches.last().unwrap();
        assert_eq!(last["x"], 479, "the release lands on the edge: {last}");
        assert!((last["y"].as_f64().unwrap() - 520.0).abs() <= 4.0, "at the pointer's height: {last}");
    });
}
