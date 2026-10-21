//! A real browser on the page: Firefox driven over WebDriver (geckodriver).
//!
//! Every test gets its own Firefox with a fresh profile (so a fresh
//! `localStorage`), opened on the instance's page. Browser tests of one test
//! binary run one at a time: each open page is one more viewer of the phone,
//! and several Firefox decoding the stream at once would only measure this
//! machine.
//!
//! Configuration (environment):
//! - `CLOUDPHONE_GECKODRIVER`: geckodriver binary (default: `geckodriver` in `PATH`);
//! - `CLOUDPHONE_FIREFOX`: Firefox binary (default: the one geckodriver finds);
//! - `CLOUDPHONE_FIREFOX_LIBS`: extra library directories for Firefox,
//!   `:`-separated, put after Firefox's own directory in `LD_LIBRARY_PATH`;
//! - `CLOUDPHONE_HEADED=1`: show the window instead of running headless.
//!
//! Elements are found the way a user perceives them: ARIA labels and roles,
//! visible text, and labels wrapping their form controls.

use crate::CloudPhone;
use fantoccini::actions::{InputSource, MouseActions, PointerAction, TouchActions, MOUSE_BUTTON_LEFT};
use fantoccini::elements::{Element, ElementRef};
use fantoccini::{Client, ClientBuilder, Locator};
use serde_json::{json, Value};
use std::future::Future;
use std::os::unix::process::CommandExt;
use std::panic::AssertUnwindSafe;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

/// One browser at a time per test binary.
static BROWSER_LOCK: Mutex<()> = Mutex::new(());

/// French labels of the toolbar buttons, as a user (or a screen reader) finds them.
pub mod fr {
    pub const POWER: &str = "Marche arrêt";
    pub const VOLUME_DOWN: &str = "Baisser le volume";
    pub const VOLUME_UP: &str = "Monter le volume";
    /// The ping and fps block: opens the information panel.
    pub const INFO: &str = "Informations : client et serveur";
    pub const RECENTS: &str = "Applications récentes";
    pub const HOME: &str = "Accueil";
    pub const BACK: &str = "Retour";
    /// The cog: opens the options panel.
    pub const OPTIONS: &str = "Options et plugins";
    pub const RECONNECT: &str = "Reconnecter la vidéo";
    pub const FULLSCREEN: &str = "Plein écran";
    pub const FOLD: &str = "Replier la barre (appui long : barre fixe)";
    pub const HANDLE: &str = "Afficher la barre (glisser pour déplacer)";
    pub const DOCKED: &str = "Barre fixe : toucher pour la rendre flottante";
    pub const CLOSE: &str = "Fermer";
    pub const CONTROLS: &str = "Contrôles Android";
    pub const NAVIGATION: &str = "Navigation Android";
    pub const SCREEN: &str = "Écran Android";
    pub const TOUCH_SURFACE: &str = "Surface tactile Android";
    /// The information panel (tabs CLIENT_TAB and SERVER_TAB) and the options panel.
    pub const INFO_PANEL: &str = "Informations";
    pub const OPTIONS_PANEL: &str = "Options";
    pub const CLIENT_TAB: &str = "Client";
    pub const SERVER_TAB: &str = "Serveur";
}

/// Colours of the connection LED (computed style).
pub mod led {
    pub const GREEN: &str = "rgb(52, 199, 89)";
    /// Waiting: something is being fixed, or connecting.
    pub const ORANGE: &str = "rgb(255, 159, 10)";
    /// Error: needs action.
    pub const RED: &str = "rgb(255, 69, 58)";
}

/// The same labels in English.
pub mod en {
    pub const POWER: &str = "Power";
    pub const VOLUME_DOWN: &str = "Volume down";
    pub const VOLUME_UP: &str = "Volume up";
    pub const INFO: &str = "Information: client and server";
    pub const RECENTS: &str = "Recent apps";
    pub const HOME: &str = "Home";
    pub const BACK: &str = "Back";
    pub const OPTIONS: &str = "Options and plugins";
    pub const RECONNECT: &str = "Reconnect the video";
    pub const FULLSCREEN: &str = "Fullscreen";
    pub const CLOSE: &str = "Close";
    pub const INFO_PANEL: &str = "Information";
    pub const OPTIONS_PANEL: &str = "Options";
    pub const CLIENT_TAB: &str = "Client";
    pub const SERVER_TAB: &str = "Server";
}

/// How to open the page.
#[derive(Clone, Debug)]
pub struct Options {
    /// The browser's preferred languages (`intl.accept_languages`).
    pub accept_language: &'static str,
    /// Wait for decoded video before handing the page to the test.
    pub wait_for_video: bool,
    /// Inner window size requested from Firefox.
    pub window: (u32, u32),
    /// Firefox's `media.autoplay.default`: 0 allows all, 1 blocks audible
    /// media (Firefox's default), 5 blocks all, until a user gesture.
    pub autoplay: u8,
}

impl Default for Options {
    fn default() -> Self {
        Options { accept_language: "fr-FR, fr", wait_for_video: true, window: (480, 960), autoplay: 0 }
    }
}

impl Options {
    pub fn without_video() -> Self {
        Options { wait_for_video: false, ..Options::default() }
    }
    pub fn english_browser() -> Self {
        Options { accept_language: "en-US, en", ..Options::default() }
    }
}

/// Runs `body` against a fresh Firefox on the page, then always closes it.
///
/// A panic in the body still closes the browser, then fails the test with
/// the body's message, the page's banners and open panels as context.
pub fn browser_test<F, Fut>(phone: &CloudPhone, options: Options, body: F)
where
    F: FnOnce(Page) -> Fut,
    Fut: Future<Output = ()>,
{
    let _serial = BROWSER_LOCK.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    let runtime = tokio::runtime::Builder::new_current_thread().enable_all().build().expect("tokio runtime");
    runtime.block_on(async move {
        let mut driver = Driver::start();
        let page = match Page::open(&driver, &options, phone.base_url()).await {
            Ok(page) => page,
            Err(error) => {
                let log = driver.log_tail();
                driver.stop();
                panic!("could not open the page in Firefox: {error}\n{log}");
            }
        };
        let outcome = futures_util::FutureExt::catch_unwind(AssertUnwindSafe(body(page.clone()))).await;
        let context = if outcome.is_err() { page.context().await } else { String::new() };
        let _ = page.client.clone().close().await;
        driver.stop();
        if let Err(panic) = outcome {
            eprintln!("--- page when the test failed ---\n{context}");
            std::panic::resume_unwind(panic);
        }
    });
}

/// geckodriver, in its own process group so Firefox goes with it.
struct Driver {
    child: Child,
    port: u16,
    log: std::path::PathBuf,
}

/// The geckodrivers this test process started, for their log files' names.
static DRIVERS: AtomicUsize = AtomicUsize::new(0);

/// The port geckodriver says it listens on, in its log ("geckodriver INFO
/// Listening on 127.0.0.1:PORT"), once it has said it.
fn listening_port(log: &std::path::Path) -> Option<u16> {
    let text = std::fs::read_to_string(log).ok()?;
    let line = text.lines().find(|line| line.contains("geckodriver") && line.contains("Listening on "))?;
    line.rsplit(':').next()?.trim().parse().ok()
}

impl Driver {
    fn start() -> Driver {
        let binary = std::env::var("CLOUDPHONE_GECKODRIVER").unwrap_or_else(|_| "geckodriver".into());
        let mut libs: Vec<String> = Vec::new();
        if let Ok(firefox) = std::env::var("CLOUDPHONE_FIREFOX") {
            if let Some(dir) = std::path::Path::new(&firefox).parent() {
                libs.push(dir.display().to_string());
            }
        }
        for var in ["CLOUDPHONE_FIREFOX_LIBS", "LD_LIBRARY_PATH"] {
            if let Ok(value) = std::env::var(var) {
                libs.extend(value.split(':').filter(|s| !s.is_empty()).map(String::from));
            }
        }
        let number = DRIVERS.fetch_add(1, Ordering::Relaxed);
        let log = std::env::temp_dir().join(format!("cloudphone-e2e-geckodriver-{}-{number}.log", std::process::id()));
        let log_file = std::fs::File::create(&log).expect("geckodriver log file");
        let mut command = Command::new(&binary);
        // Port 0: geckodriver binds a port the kernel picks and says which in
        // its log (at info), so no other process can take it in between.
        command
            .args(["--port", "0", "--log", "info"])
            .env("LD_LIBRARY_PATH", libs.join(":"))
            .stdin(Stdio::null())
            .stdout(log_file.try_clone().unwrap())
            .stderr(log_file)
            .process_group(0);
        let mut child = command.spawn().unwrap_or_else(|e| {
            panic!("cannot start geckodriver ({binary}): {e}. Set CLOUDPHONE_GECKODRIVER, see tests/e2e/README.md")
        });
        let started = Instant::now();
        let port = loop {
            if let Some(port) = listening_port(&log) {
                break port;
            }
            if let Ok(Some(status)) = child.try_wait() {
                panic!("geckodriver exited ({status}) before listening: {}", std::fs::read_to_string(&log).unwrap_or_default());
            }
            assert!(started.elapsed() < Duration::from_secs(20), "geckodriver did not say where it listens");
            std::thread::sleep(Duration::from_millis(50));
        };
        while std::net::TcpStream::connect(("127.0.0.1", port)).is_err() {
            assert!(started.elapsed() < Duration::from_secs(20), "geckodriver did not listen on {port}");
            std::thread::sleep(Duration::from_millis(50));
        }
        Driver { child, port, log }
    }

    fn stop(&mut self) {
        // The whole group: geckodriver and the Firefox it started.
        unsafe {
            libc::killpg(self.child.id() as i32, libc::SIGTERM);
        }
        let _ = self.child.wait();
        let _ = std::fs::remove_file(&self.log);
    }

    fn log_tail(&self) -> String {
        let log = std::fs::read_to_string(&self.log).unwrap_or_default();
        let lines: Vec<&str> = log.lines().collect();
        lines[lines.len().saturating_sub(30)..].join("\n")
    }
}

/// The page in one Firefox.
#[derive(Clone)]
pub struct Page {
    pub client: Client,
    /// The page's URL.
    pub base: String,
}

impl Page {
    async fn open(driver: &Driver, options: &Options, base: &str) -> Result<Page, String> {
        let mut args = vec![format!("--width={}", options.window.0), format!("--height={}", options.window.1)];
        if std::env::var("CLOUDPHONE_HEADED").map(|v| v != "1").unwrap_or(true) {
            args.push("-headless".into());
        }
        let mut firefox = json!({
            "args": args,
            "prefs": {
                "intl.accept_languages": options.accept_language,
                "media.autoplay.default": options.autoplay,
                "media.autoplay.blocking_policy": 0,
                "full-screen-api.warning.timeout": 0,
                "full-screen-api.transition-duration.enter": "0 0",
                "full-screen-api.transition-duration.leave": "0 0",
                "browser.shell.checkDefaultBrowser": false,
                // WebRTC with a local peer (the fake emulator): plain host
                // candidates instead of mDNS names nothing here resolves.
                "media.peerconnection.ice.obfuscate_host_addresses": false,
            },
        });
        if let Ok(binary) = std::env::var("CLOUDPHONE_FIREFOX") {
            firefox["binary"] = json!(binary);
        }
        let mut capabilities = serde_json::Map::new();
        capabilities.insert("browserName".into(), json!("firefox"));
        capabilities.insert("moz:firefoxOptions".into(), firefox);
        // geckodriver is local plain HTTP: no TLS stack needed.
        let client = ClientBuilder::new(hyper_util::client::legacy::connect::HttpConnector::new())
            .capabilities(capabilities)
            .connect(&format!("http://127.0.0.1:{}", driver.port))
            .await
            .map_err(|e| format!("WebDriver session: {e}"))?;
        let page = Page { client, base: base.to_string() };
        page.client.goto(base).await.map_err(|e| format!("open {base}: {e}"))?;
        page.wait_for_any_label(&[fr::POWER, en::POWER], Duration::from_secs(30)).await;
        if options.wait_for_video {
            page.wait_for_video(Duration::from_secs(45)).await;
        }
        Ok(page)
    }

    /// Runs a script (with `return`) and gives its JSON value.
    pub async fn js(&self, script: &str, args: Vec<Value>) -> Value {
        self.client.execute(script, args).await.unwrap_or_else(|e| panic!("script failed: {e}\n{script}"))
    }

    /// Polls a script until it returns something truthy, which it gives back.
    pub async fn wait_js(&self, what: &str, timeout: Duration, script: &str, args: Vec<Value>) -> Value {
        let start = Instant::now();
        let mut last = Value::Null;
        loop {
            if let Ok(value) = self.client.execute(script, args.clone()).await {
                if truthy(&value) {
                    return value;
                }
                last = value;
            }
            if start.elapsed() > timeout {
                panic!("timed out after {timeout:?} waiting for {what} (last value: {last})");
            }
            tokio::time::sleep(Duration::from_millis(250)).await;
        }
    }

    pub async fn sleep(&self, duration: Duration) {
        tokio::time::sleep(duration).await;
    }

    pub async fn reload(&self, wait_for_video: bool) {
        self.client.refresh().await.expect("reload the page");
        self.wait_for_any_label(&[fr::POWER, en::POWER], Duration::from_secs(30)).await;
        if wait_for_video {
            self.wait_for_video(Duration::from_secs(45)).await;
        }
    }

    // ---- finding things the way a user does ----

    /// The element whose `aria-label` is exactly `label`.
    pub async fn by_label(&self, label: &str) -> Element {
        self.client
            .find(Locator::Css(&css_label(label)))
            .await
            .unwrap_or_else(|e| panic!("no element labelled {label:?}: {e}"))
    }

    pub async fn has_label(&self, label: &str) -> bool {
        self.client.find_all(Locator::Css(&css_label(label))).await.map(|v| !v.is_empty()).unwrap_or(false)
    }

    /// True when the labelled element exists and takes room on screen.
    pub async fn label_visible(&self, label: &str) -> bool {
        self.js(
            "const e = document.querySelector(arguments[0]); if (!e) return false; \
             const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden';",
            vec![json!(css_label(label))],
        )
        .await
            == json!(true)
    }

    pub async fn wait_for_label(&self, label: &str, timeout: Duration) -> Element {
        self.wait_js(&format!("an element labelled {label:?}"), timeout, "return !!document.querySelector(arguments[0])", vec![json!(css_label(label))])
            .await;
        self.by_label(label).await
    }

    pub async fn wait_for_any_label(&self, labels: &[&str], timeout: Duration) {
        let selectors: Vec<Value> = labels.iter().map(|l| json!(css_label(l))).collect();
        self.wait_js(&format!("one of {labels:?}"), timeout, "return arguments[0].some(s => document.querySelector(s))", vec![json!(selectors)]).await;
    }

    pub async fn wait_label_gone(&self, label: &str, timeout: Duration) {
        self.wait_js(&format!("{label:?} to go away"), timeout, "return !document.querySelector(arguments[0])", vec![json!(css_label(label))]).await;
    }

    pub async fn wait_label_visible(&self, label: &str, visible: bool, timeout: Duration) {
        self.wait_js(
            &format!("{label:?} to be {}", if visible { "visible" } else { "hidden" }),
            timeout,
            "const e = document.querySelector(arguments[0]); \
             const v = !!e && e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().height > 0; return v === arguments[1];",
            vec![json!(css_label(label)), json!(visible)],
        )
        .await;
    }

    /// Clicks the labelled element as a user would (WebDriver click).
    pub async fn click_label(&self, label: &str) {
        self.by_label(label).await.click().await.unwrap_or_else(|e| panic!("click {label:?}: {e}"));
    }

    /// The `aria-label`s of the buttons in the toolbar, in order.
    pub async fn toolbar_labels(&self) -> Vec<String> {
        let value = self
            .js("const n = document.querySelector('nav'); return n ? [...n.querySelectorAll('button')].map(b => b.getAttribute('aria-label')) : []", vec![])
            .await;
        strings(&value)
    }

    /// Text of the labelled element (innerText).
    pub async fn text_of(&self, label: &str) -> String {
        self.js("const e = document.querySelector(arguments[0]); return e ? e.innerText : null", vec![json!(css_label(label))])
            .await
            .as_str()
            .unwrap_or_else(|| panic!("no element labelled {label:?}"))
            .to_string()
    }

    // ---- panels (role=dialog) ----

    pub async fn open_dialogs(&self) -> Vec<String> {
        strings(&self.js("return [...document.querySelectorAll('[role=dialog]')].map(d => d.getAttribute('aria-label'))", vec![]).await)
    }

    /// Opens the information panel (from its toolbar block, in either
    /// language) on `tab` (e.g. [`fr::SERVER_TAB`]); gives the panel's name.
    pub async fn open_info(&self, tab: &str) -> String {
        let (block, panel) = if self.has_label(fr::INFO).await { (fr::INFO, fr::INFO_PANEL) } else { (en::INFO, en::INFO_PANEL) };
        if !self.open_dialogs().await.iter().any(|d| d == panel) {
            self.click_label(block).await;
            self.wait_dialog(panel).await;
        }
        self.wait_js(
            &format!("the {tab:?} tab"),
            Duration::from_secs(10),
            "const t = [...document.querySelectorAll('[role=dialog] [role=tab]')].find(t => t.innerText.trim() === arguments[0]); \
             if (!t) return false; if (t.getAttribute('aria-selected') !== 'true') { t.click(); return false; } return true",
            vec![json!(tab)],
        )
        .await;
        panel.to_string()
    }

    /// Opens the options panel (cog, either language); gives its name.
    pub async fn open_options(&self) -> String {
        let (button, panel) = if self.has_label(fr::OPTIONS).await { (fr::OPTIONS, fr::OPTIONS_PANEL) } else { (en::OPTIONS, en::OPTIONS_PANEL) };
        if !self.open_dialogs().await.iter().any(|d| d == panel) {
            self.click_label(button).await;
            self.wait_dialog(panel).await;
        }
        panel.to_string()
    }

    pub async fn wait_dialog(&self, name: &str) {
        self.wait_js(&format!("panel {name:?}"), Duration::from_secs(10), "return !!document.querySelector(arguments[0])", vec![json!(dialog_css(name))]).await;
    }

    pub async fn wait_no_dialog(&self) {
        self.wait_js("every panel to close", Duration::from_secs(10), "return !document.querySelector('[role=dialog]')", vec![]).await;
    }

    /// The panel's visible text.
    pub async fn dialog_text(&self, name: &str) -> String {
        self.js("const d = document.querySelector(arguments[0]); return d ? d.innerText : ''", vec![json!(dialog_css(name))])
            .await
            .as_str()
            .unwrap_or_default()
            .to_string()
    }

    /// The panel's section headings and rows, as `[(label, value)]` read from
    /// its text: a line followed by its value line.
    pub async fn dialog_lines(&self, name: &str) -> Vec<String> {
        self.dialog_text(name).await.lines().map(|l| l.trim().to_string()).filter(|l| !l.is_empty()).collect()
    }

    /// The value shown under a row label of a panel (the next text line).
    pub async fn dialog_value(&self, name: &str, row: &str) -> Option<String> {
        // Rows only: the tab panel's text when the panel has tabs (a tab
        // may be named like a row, "Serveur").
        let text = self
            .js(
                "const d = document.querySelector(arguments[0]); if (!d) return ''; const p = d.querySelector('[role=tabpanel]'); return (p || d).innerText",
                vec![json!(dialog_css(name))],
            )
            .await;
        let lines: Vec<String> = text.as_str().unwrap_or_default().lines().map(|l| l.trim().to_string()).filter(|l| !l.is_empty()).collect();
        lines.iter().position(|l| l == row).and_then(|i| lines.get(i + 1).cloned())
    }

    /// Waits until a row of the panel shows a value accepted by `accept`.
    pub async fn wait_dialog_value(&self, name: &str, row: &str, timeout: Duration, accept: impl Fn(&str) -> bool) -> String {
        let start = Instant::now();
        loop {
            let value = self.dialog_value(name, row).await;
            if let Some(v) = &value {
                if accept(v) {
                    return v.clone();
                }
            }
            if start.elapsed() > timeout {
                panic!("panel {name:?}, row {row:?}: no acceptable value after {timeout:?} (last: {value:?})\n{}", self.dialog_text(name).await);
            }
            tokio::time::sleep(Duration::from_millis(300)).await;
        }
    }

    /// The form control wrapped by the label whose own text starts with `label`, inside the panel.
    pub async fn control(&self, dialog: &str, label: &str) -> Element {
        let value = self
            .js(
                "const d = document.querySelector(arguments[0]); if (!d) return null; \
                 const own = l => [...l.childNodes].filter(n => n.nodeType === 3 || (n.tagName && !['SELECT','INPUT','OPTION'].includes(n.tagName))).map(n => n.textContent).join('').trim(); \
                 const l = [...d.querySelectorAll('label')].find(l => own(l).startsWith(arguments[1]) || l.innerText.trim().split('\\n')[0].trim() === arguments[1]); \
                 return l ? l.control : null;",
                vec![json!(dialog_css(dialog)), json!(label)],
            )
            .await;
        element_from(&self.client, &value).unwrap_or_else(|| panic!("panel {dialog:?} has no control labelled {label:?}"))
    }

    /// `value` and `checked` of a control, and its `<option>`s (`value:text`).
    pub async fn control_state(&self, control: &Element) -> Value {
        self.js(
            "const e = arguments[0]; return {value: e.value, checked: e.checked, disabled: e.disabled, \
             options: e.options ? [...e.options].map(o => o.value + ':' + o.text) : null}",
            vec![serde_json::to_value(control).unwrap()],
        )
        .await
    }

    /// The buttons of a panel whose text is exactly `text`, with their `disabled` state.
    pub async fn dialog_buttons(&self, dialog: &str, text: &str) -> Vec<bool> {
        let v = self
            .js(
                "const d = document.querySelector(arguments[0]); return d ? [...d.querySelectorAll('button')].filter(b => b.innerText.trim() === arguments[1]).map(b => b.disabled) : []",
                vec![json!(dialog_css(dialog)), json!(text)],
            )
            .await;
        v.as_array().map(|a| a.iter().map(|b| b.as_bool().unwrap_or(false)).collect()).unwrap_or_default()
    }

    /// The "Appliquer"/"Apply" button that follows `control` in the panel,
    /// and the text from the control's label up to it: the control's own
    /// form, whatever the panel's layout (one or several forms).
    async fn section_of(&self, control: &Element, what: &str) -> Value {
        self.js(
            "const c = arguments[0]; const d = c.closest('[role=dialog]'); if (!d) return null; \
             const b = [...d.querySelectorAll('button')].find(b => ['Appliquer', 'Apply'].includes(b.innerText.trim()) \
               && (c.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)); if (!b) return null; \
             if (arguments[1] !== 'text') return b.disabled; \
             const r = document.createRange(); r.setStartBefore(c.closest('label') || c); r.setEndAfter(b); \
             const div = document.createElement('div'); div.appendChild(r.cloneContents()); \
             div.querySelectorAll('select, option').forEach(o => o.remove()); return div.textContent;",
            vec![serde_json::to_value(control).unwrap(), json!(what)],
        )
        .await
    }

    /// Whether the Apply button of the control's section is disabled.
    pub async fn apply_disabled_for(&self, control: &Element) -> bool {
        self.section_of(control, "disabled").await.as_bool().expect("an Apply button near the control")
    }

    /// The text of the control's section (from the control up to its Apply button).
    pub async fn section_text_for(&self, control: &Element) -> String {
        self.section_of(control, "text").await.as_str().unwrap_or_default().to_string()
    }

    // ---- banners (role=status) ----

    /// Texts of the banners on the screen.
    pub async fn banners(&self) -> Vec<String> {
        strings(&self.js("return [...document.querySelectorAll('[role=status]')].map(b => b.innerText.trim())", vec![]).await)
    }

    /// Closes the banner containing `text` with its cross.
    pub async fn close_banner(&self, text: &str) {
        let value = self
            .js(
                "const b = [...document.querySelectorAll('[role=status]')].find(b => b.innerText.includes(arguments[0])); \
                 return b ? b.querySelector('button[aria-label]') : null",
                vec![json!(text)],
            )
            .await;
        let cross = element_from(&self.client, &value).unwrap_or_else(|| panic!("no closable banner with {text:?}"));
        cross.click().await.expect("click the banner's cross");
    }

    // ---- video ----

    /// `{w, h, t, paused, frames, cssW, cssH}` of the video element.
    pub async fn video(&self) -> Value {
        self.js(
            "const v = document.querySelector('video'); if (!v) return null; const r = v.getBoundingClientRect(); \
             const q = v.getVideoPlaybackQuality ? v.getVideoPlaybackQuality() : {}; \
             return {w: v.videoWidth, h: v.videoHeight, t: v.currentTime, paused: v.paused, frames: q.totalVideoFrames || 0, cssW: r.width, cssH: r.height, x: r.x, y: r.y}",
            vec![],
        )
        .await
    }

    pub async fn wait_for_video(&self, timeout: Duration) {
        self.wait_js(
            "decoded video (videoWidth > 0 and playing)",
            timeout,
            "const v = document.querySelector('video'); return !!v && v.videoWidth > 0 && !v.paused && v.currentTime > 0",
            vec![],
        )
        .await;
    }

    /// The current video frame, downscaled to `cols` columns, as luminance (0-255).
    pub async fn frame(&self, cols: u32) -> Frame {
        let value = self
            .js(
                "const v = document.querySelector('video'); if (!v || !v.videoWidth) return null; \
                 const W = arguments[0], H = Math.round(W * v.videoHeight / v.videoWidth); \
                 const c = document.createElement('canvas'); c.width = W; c.height = H; \
                 const g = c.getContext('2d', {willReadFrequently: true}); g.drawImage(v, 0, 0, W, H); \
                 const d = g.getImageData(0, 0, W, H).data; const out = new Array(W * H); \
                 for (let i = 0; i < W * H; i++) out[i] = Math.round((d[4*i] * 299 + d[4*i+1] * 587 + d[4*i+2] * 114) / 1000); \
                 return {w: W, h: H, l: out}",
                vec![json!(cols)],
            )
            .await;
        Frame {
            width: value["w"].as_u64().expect("a video frame") as usize,
            height: value["h"].as_u64().unwrap() as usize,
            luma: value["l"].as_array().unwrap().iter().map(|v| v.as_u64().unwrap() as u8).collect(),
        }
    }

    // ---- gestures ----

    /// Mouse press on the element's centre, held `hold`, released.
    pub async fn long_press(&self, element: &Element, hold: Duration) {
        let mouse = MouseActions::new("mouse".into())
            .then(PointerAction::MoveToElement { element: element.clone(), duration: None, x: 0.0, y: 0.0 })
            .then(PointerAction::Down { button: MOUSE_BUTTON_LEFT })
            .then(PointerAction::Pause { duration: hold })
            .then(PointerAction::Up { button: MOUSE_BUTTON_LEFT });
        self.client.perform_actions(mouse).await.expect("long press");
        let _ = self.client.release_actions().await;
    }

    /// Mouse drag from the element's centre by (dx, dy).
    pub async fn drag(&self, element: &Element, dx: f64, dy: f64) {
        let mouse = MouseActions::new("mouse".into())
            .then(PointerAction::MoveToElement { element: element.clone(), duration: None, x: 0.0, y: 0.0 })
            .then(PointerAction::Down { button: MOUSE_BUTTON_LEFT })
            .then(PointerAction::MoveBy { duration: Some(Duration::from_millis(150)), x: dx / 3.0, y: dy / 3.0 })
            .then(PointerAction::MoveBy { duration: Some(Duration::from_millis(150)), x: dx / 3.0, y: dy / 3.0 })
            .then(PointerAction::MoveBy { duration: Some(Duration::from_millis(150)), x: dx - 2.0 * (dx / 3.0), y: dy - 2.0 * (dy / 3.0) })
            .then(PointerAction::Up { button: MOUSE_BUTTON_LEFT });
        self.client.perform_actions(mouse).await.expect("drag");
        let _ = self.client.release_actions().await;
    }

    /// A finger swipe in viewport coordinates.
    pub async fn swipe(&self, from: (f64, f64), to: (f64, f64), duration: Duration) {
        let steps = 8;
        let mut finger = TouchActions::new("finger".into())
            .then(PointerAction::MoveTo { duration: None, x: from.0, y: from.1 })
            .then(PointerAction::Down { button: MOUSE_BUTTON_LEFT });
        for i in 1..=steps {
            let f = i as f64 / steps as f64;
            finger = finger.then(PointerAction::MoveTo {
                duration: Some(duration / steps),
                x: from.0 + (to.0 - from.0) * f,
                y: from.1 + (to.1 - from.1) * f,
            });
        }
        finger = finger.then(PointerAction::Up { button: MOUSE_BUTTON_LEFT });
        self.client.perform_actions(finger).await.expect("swipe");
        let _ = self.client.release_actions().await;
    }

    /// A mouse click (press, release) at viewport coordinates.
    pub async fn click_at(&self, x: f64, y: f64) {
        let mouse = MouseActions::new("mouse".into())
            .then(PointerAction::MoveTo { duration: None, x, y })
            .then(PointerAction::Down { button: MOUSE_BUTTON_LEFT })
            .then(PointerAction::Pause { duration: Duration::from_millis(80) })
            .then(PointerAction::Up { button: MOUSE_BUTTON_LEFT });
        self.client.perform_actions(mouse).await.expect("click");
        let _ = self.client.release_actions().await;
    }

    /// Presses the mouse button at viewport coordinates and keeps it down
    /// until [`Page::release`].
    pub async fn press_at(&self, x: f64, y: f64) {
        let mouse = MouseActions::new("mouse".into())
            .then(PointerAction::MoveTo { duration: None, x, y })
            .then(PointerAction::Down { button: MOUSE_BUTTON_LEFT });
        self.client.perform_actions(mouse).await.expect("press");
    }

    /// Releases the button pressed by [`Page::press_at`].
    pub async fn release(&self) {
        let mouse = MouseActions::new("mouse".into()).then(PointerAction::Up { button: MOUSE_BUTTON_LEFT });
        self.client.perform_actions(mouse).await.expect("release");
        let _ = self.client.release_actions().await;
    }

    /// Where Android's pixel (x, y) is in the viewport, for a screen of
    /// `display` (width, height) Android pixels: through the touch surface,
    /// as the page maps it.
    pub async fn viewport_point(&self, display: (u64, u64), x: u64, y: u64) -> (f64, f64) {
        let rect = self.rect(&css_label(fr::TOUCH_SURFACE)).await;
        let (left, top, w, h) = (rect["x"].as_f64().unwrap(), rect["y"].as_f64().unwrap(), rect["w"].as_f64().unwrap(), rect["h"].as_f64().unwrap());
        (left + (x as f64 + 0.5) * w / display.0 as f64, top + (y as f64 + 0.5) * h / display.1 as f64)
    }

    /// Waits until a status (banner or covering message, role=status)
    /// contains `text`; gives its whole text.
    pub async fn wait_status(&self, text: &str, timeout: Duration) -> String {
        let found = self
            .wait_js(
                &format!("a status saying {text:?}"),
                timeout,
                "const b = [...document.querySelectorAll('[role=status]')].find(b => b.innerText.includes(arguments[0])); return b ? b.innerText : null",
                vec![json!(text)],
            )
            .await;
        found.as_str().unwrap_or_default().to_string()
    }

    /// Waits until no status contains `text`.
    pub async fn wait_no_status(&self, text: &str, timeout: Duration) {
        self.wait_js(
            &format!("no status saying {text:?}"),
            timeout,
            "return ![...document.querySelectorAll('[role=status]')].some(b => b.innerText.includes(arguments[0]))",
            vec![json!(text)],
        )
        .await;
    }

    /// Whether the status containing `text` covers the screen (no close
    /// cross) or is a closable banner.
    pub async fn status_is_closable(&self, text: &str) -> bool {
        self.js(
            "const b = [...document.querySelectorAll('[role=status]')].find(b => b.innerText.includes(arguments[0])); \
             return !!b && !!b.querySelector('button[aria-label]')",
            vec![json!(text)],
        )
        .await
            == json!(true)
    }

    /// The connection LED: `{label, colour}` ("Connexion connected", "rgb(…)").
    pub async fn led(&self) -> Value {
        self.js(
            "const l = document.querySelector('[aria-label^=\"Connexion \"], [aria-label^=\"Connection \"]'); \
             return l ? {label: l.getAttribute('aria-label'), colour: getComputedStyle(l).backgroundColor} : null",
            vec![],
        )
        .await
    }

    /// Waits until the LED has `colour` (one of the constants in [`led`]).
    pub async fn wait_led(&self, colour: &str, timeout: Duration) {
        self.wait_js(
            &format!("the LED to turn {colour}"),
            timeout,
            "const l = document.querySelector('[aria-label^=\"Connexion \"], [aria-label^=\"Connection \"]'); \
             return !!l && getComputedStyle(l).backgroundColor === arguments[0]",
            vec![json!(colour)],
        )
        .await;
    }

    // ---- settings in this browser ----

    /// The page's stored settings (`localStorage['cloudphone.settings']`), parsed.
    pub async fn stored_settings(&self) -> Value {
        let raw = self.js("return localStorage.getItem('cloudphone.settings')", vec![]).await;
        raw.as_str().map(|s| serde_json::from_str(s).unwrap_or(Value::Null)).unwrap_or(Value::Null)
    }

    pub async fn fullscreen_element(&self) -> Option<String> {
        self.js("return document.fullscreenElement ? document.fullscreenElement.tagName : null", vec![]).await.as_str().map(String::from)
    }

    /// Bounding rectangle of the first element matching a CSS selector: `{x, y, w, h, position, display}`.
    pub async fn rect(&self, css: &str) -> Value {
        self.js(
            "const e = document.querySelector(arguments[0]); if (!e) return null; const r = e.getBoundingClientRect(); const s = getComputedStyle(e); \
             return {x: r.x, y: r.y, w: r.width, h: r.height, position: s.position, display: s.display}",
            vec![json!(css)],
        )
        .await
    }

    /// What a failing test should print: banners, open panels, video and stored settings.
    pub async fn context(&self) -> String {
        let summary = self
            .client
            .execute(
                "const v = document.querySelector('video'); \
                 return {url: location.href, banners: [...document.querySelectorAll('[role=status]')].map(b => b.innerText), \
                 dialogs: [...document.querySelectorAll('[role=dialog]')].map(d => d.innerText.slice(0, 1500)), \
                 toolbar: [...document.querySelectorAll('nav button')].map(b => b.getAttribute('aria-label') + ' ' + b.innerText), \
                 video: v ? {w: v.videoWidth, h: v.videoHeight, t: v.currentTime, paused: v.paused} : null, \
                 settings: localStorage.getItem('cloudphone.settings'), fullscreen: !!document.fullscreenElement}",
                vec![],
            )
            .await;
        match summary {
            Ok(value) => serde_json::to_string_pretty(&value).unwrap_or_default(),
            Err(e) => format!("(page unavailable: {e})"),
        }
    }
}

/// A downscaled luminance image of the video.
#[derive(Clone, Debug)]
pub struct Frame {
    pub width: usize,
    pub height: usize,
    pub luma: Vec<u8>,
}

impl Frame {
    /// Share of pixels, in a region given in fractions of the frame
    /// `(x0, y0, x1, y1)`, whose luminance differs by more than `threshold`.
    pub fn changed(&self, other: &Frame, region: (f64, f64, f64, f64), threshold: u8) -> f64 {
        assert_eq!((self.width, self.height), (other.width, other.height), "frames of the same size");
        let (x0, x1) = ((region.0 * self.width as f64) as usize, (region.2 * self.width as f64) as usize);
        let (y0, y1) = ((region.1 * self.height as f64) as usize, (region.3 * self.height as f64) as usize);
        let mut changed = 0usize;
        let mut total = 0usize;
        for y in y0..y1.min(self.height) {
            for x in x0..x1.min(self.width) {
                let i = y * self.width + x;
                total += 1;
                if self.luma[i].abs_diff(other.luma[i]) > threshold {
                    changed += 1;
                }
            }
        }
        if total == 0 { 0.0 } else { changed as f64 / total as f64 }
    }

    pub fn mean(&self) -> f64 {
        self.luma.iter().map(|&v| v as f64).sum::<f64>() / self.luma.len().max(1) as f64
    }
}

/// `[aria-label="…"]` for an exact label.
pub fn css_label(label: &str) -> String {
    format!("[aria-label=\"{}\"]", label.replace('\\', "\\\\").replace('"', "\\\""))
}

fn dialog_css(name: &str) -> String {
    format!("[role=dialog]{}", css_label(name))
}

fn truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().map(|f| f != 0.0).unwrap_or(true),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(_) => true,
    }
}

pub fn strings(value: &Value) -> Vec<String> {
    value.as_array().map(|a| a.iter().map(|v| v.as_str().unwrap_or("").to_string()).collect()).unwrap_or_default()
}

fn element_from(client: &Client, value: &Value) -> Option<Element> {
    let id = value.as_object()?.values().next()?.as_str()?.to_string();
    Some(Element::from_element_id(client.clone(), ElementRef::from(id)))
}

/// Parses the leading number of a text such as "20ms" or "13fps".
pub fn leading_number(text: &str) -> Option<f64> {
    let digits: String = text.trim().chars().take_while(|c| c.is_ascii_digit() || *c == '.').collect();
    digits.parse().ok()
}

/// Runs blocking code (the HTTP helpers of this crate) from a browser test's
/// async body, on its own thread.
pub fn blocking<T: Send + 'static>(f: impl FnOnce() -> T + Send + 'static) -> T {
    std::thread::spawn(f).join().unwrap_or_else(|panic| std::panic::resume_unwind(panic))
}

/// Every "W×H" size written in a text, in order.
pub fn sizes_in(text: &str) -> Vec<(u64, u64)> {
    let chars: Vec<char> = text.chars().collect();
    let mut sizes = Vec::new();
    for (i, &c) in chars.iter().enumerate() {
        if c != '×' {
            continue;
        }
        let mut a = i;
        while a > 0 && chars[a - 1].is_ascii_digit() {
            a -= 1;
        }
        let mut b = i + 1;
        while b < chars.len() && chars[b].is_ascii_digit() {
            b += 1;
        }
        if a < i && b > i + 1 {
            let w: String = chars[a..i].iter().collect();
            let h: String = chars[i + 1..b].iter().collect();
            sizes.push((w.parse().unwrap(), h.parse().unwrap()));
        }
    }
    sizes
}
