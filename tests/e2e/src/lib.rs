//! Black-box helpers for end-to-end tests of Cloud Phone.
//!
//! The tests only know what a user's browser can reach: the page and its
//! HTTP and WebSocket API. They never read the application's code or the
//! server's files.
//!
//! By default every test starts its own instance: the repository's gateway
//! and page on a fake emulator (`tests/fake-emulator`), on free local ports
//! ([`CloudPhone::start`]). The fake also answers what Android received and
//! takes orders no real phone can take on demand (crash, not booted, stream
//! dropped...): [`Fake`].
//!
//! The `smoke` feature adds the tests that run against a deployed instance
//! at `CLOUDPHONE_URL` ([`CloudPhone::remote`]); nothing else ever reads
//! that variable.

pub mod browser;
pub mod fake;

pub use fake::Fake;
use serde_json::Value;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tungstenite::Message;

/// One Cloud Phone instance under test: a gateway and page on a fake
/// emulator, or a deployed instance (smoke tests). Cheap to clone; the fake
/// and its gateway stop when the last clone goes.
#[derive(Clone)]
pub struct CloudPhone {
    inner: Arc<Inner>,
}

struct Inner {
    base: String,
    fake: Option<Fake>,
}

impl CloudPhone {
    /// A fresh gateway and page on a fake emulator with its defaults
    /// (Android booted, 480×1040 at density 213, lavapipe, 4 cores, 4 GiB).
    pub fn start() -> CloudPhone {
        CloudPhone::start_with(serde_json::json!({}))
    }

    /// Same, with the fake's initial state changed: see `DEFAULTS` in
    /// `tests/fake-emulator/fake_emulator.py` (`display`, `settings`,
    /// `options`, `unit`, `booted`, `grpc`, `load`).
    pub fn start_with(config: Value) -> CloudPhone {
        let fake = Fake::start(config);
        let base = format!("http://127.0.0.1:{}/", fake.web_port);
        CloudPhone { inner: Arc::new(Inner { base, fake: Some(fake) }) }
    }

    /// The deployed instance at `CLOUDPHONE_URL`: smoke and contract tests only.
    pub fn remote() -> CloudPhone {
        let url = std::env::var("CLOUDPHONE_URL")
            .expect("set CLOUDPHONE_URL to the page of the deployed instance, e.g. http://<server>:8000/");
        let base = if url.ends_with('/') { url } else { format!("{url}/") };
        CloudPhone { inner: Arc::new(Inner { base, fake: None }) }
    }

    /// The instance a contract test checks: the deployed one with the
    /// `smoke` feature, a fake otherwise (the fake must pass them too).
    pub fn contract_target() -> CloudPhone {
        if cfg!(feature = "smoke") { CloudPhone::remote() } else { CloudPhone::start() }
    }

    /// Base URL, always ending with "/".
    pub fn base_url(&self) -> &str {
        &self.inner.base
    }

    /// The fake emulator behind this instance (panics on a deployed one).
    pub fn fake(&self) -> &Fake {
        self.inner.fake.as_ref().expect("this test needs the fake emulator, not a deployed instance")
    }

    pub fn is_fake(&self) -> bool {
        self.inner.fake.is_some()
    }

    pub fn url(&self, path: &str) -> String {
        format!("{}{}", self.inner.base, path.trim_start_matches('/'))
    }

    pub fn ws_url(&self, path: &str) -> String {
        self.url(path).replacen("http", "ws", 1)
    }

    pub fn get(&self, path: &str) -> Answer {
        let url = self.url(path);
        let path = path.to_string();
        off_runtime(move || Answer::read(client().get(url).send().unwrap_or_else(|e| panic!("GET {path}: {e}"))))
    }

    pub fn get_json(&self, path: &str) -> Value {
        let url = self.url(path);
        let path = path.to_string();
        off_runtime(move || {
            let response = client().get(url).send().unwrap_or_else(|e| panic!("GET {path}: {e}"));
            assert!(response.status().is_success(), "GET {path}: HTTP {}", response.status());
            response.json().unwrap_or_else(|e| panic!("GET {path}: not JSON: {e}"))
        })
    }

    /// GET as JSON, or None while the gateway does not answer (it may be
    /// restarting) or answers an error: for polling loops.
    pub fn try_get_json(&self, path: &str) -> Option<Value> {
        let url = self.url(path);
        off_runtime(move || {
            let response = client().get(url).send().ok()?;
            if !response.status().is_success() {
                return None;
            }
            response.json().ok()
        })
    }

    /// The per-start token the page carries in `<meta name="cloudphone-token">`,
    /// as a browser would read it.
    pub fn page_token(&self) -> String {
        let url = self.url("");
        let page = off_runtime(move || client().get(url).send().and_then(|r| r.text()).expect("page body"));
        let marker = "name=\"cloudphone-token\" content=\"";
        let start = page.find(marker).expect("the page carries a cloudphone-token meta tag") + marker.len();
        let end = page[start..].find('"').expect("closing quote of the token") + start;
        page[start..end].to_string()
    }

    /// POST as the page does: JSON body and the page's token.
    pub fn post_json(&self, path: &str, body: &Value) -> Answer {
        let (url, token, body, path) = (self.url(path), self.page_token(), body.clone(), path.to_string());
        off_runtime(move || {
            Answer::read(client().post(url).header("X-CloudPhone-Token", token).json(&body).send().unwrap_or_else(|e| panic!("POST {path}: {e}")))
        })
    }

    /// Number of viewers the server reports now.
    pub fn viewers(&self) -> u64 {
        self.get_json("api/v1/state?viewer=e2e-count")["viewers"].as_u64().expect("state.viewers")
    }

    /// Polls the viewer count until `accept` holds; gives the last count.
    pub fn wait_viewers(&self, what: &str, timeout: Duration, accept: impl Fn(u64) -> bool) -> u64 {
        let start = Instant::now();
        loop {
            let last = self.viewers();
            if accept(last) {
                return last;
            }
            assert!(start.elapsed() < timeout, "timed out after {timeout:?} waiting for {what}; viewers = {last}");
            std::thread::sleep(Duration::from_millis(300));
        }
    }

    /// Waits until the server reports Android booted and answering.
    pub fn wait_for_android(&self, timeout: Duration) {
        wait_for("Android to boot", timeout, || {
            let url = self.url("api/v1/state");
            let state: Value = off_runtime(move || client().get(url).send().ok()?.json().ok())?;
            (state["android"]["booted"] == Value::Bool(true)).then_some(())
        });
    }

    /// Waits until the gateway answers with another page token than `old`
    /// (it restarted), and gives the new one.
    pub fn wait_new_token(&self, old: &str, timeout: Duration) -> String {
        wait_for("the gateway to restart with a new token", timeout, || {
            let url = self.url("");
            let page = off_runtime(move || client().get(url).send().ok()?.text().ok())?;
            let marker = "name=\"cloudphone-token\" content=\"";
            let start = page.find(marker)? + marker.len();
            let token = page[start..start + page[start..].find('"')?].to_string();
            (token != old).then_some(token)
        })
    }
}

/// An HTTP answer, read whole: usable anywhere, also in a browser test's
/// async body (a blocking reqwest response is not).
#[derive(Debug, Clone)]
pub struct Answer {
    status: reqwest::StatusCode,
    headers: reqwest::header::HeaderMap,
    body: Vec<u8>,
}

impl Answer {
    pub fn read(response: reqwest::blocking::Response) -> Answer {
        let status = response.status();
        let headers = response.headers().clone();
        let body = response.bytes().map(|b| b.to_vec()).unwrap_or_default();
        Answer { status, headers, body }
    }
    pub fn status(&self) -> reqwest::StatusCode {
        self.status
    }
    pub fn headers(&self) -> &reqwest::header::HeaderMap {
        &self.headers
    }
    pub fn json(&self) -> Result<Value, serde_json::Error> {
        serde_json::from_slice(&self.body)
    }
    pub fn text(&self) -> Result<String, std::string::FromUtf8Error> {
        String::from_utf8(self.body.clone())
    }
    pub fn bytes(&self) -> &[u8] {
        &self.body
    }
}

/// Runs blocking code (reqwest's blocking client) from anywhere: on its own
/// thread when called from a browser test's async body.
pub fn off_runtime<T: Send + 'static>(f: impl FnOnce() -> T + Send + 'static) -> T {
    if tokio::runtime::Handle::try_current().is_ok() {
        std::thread::spawn(f).join().unwrap_or_else(|panic| std::panic::resume_unwind(panic))
    } else {
        f()
    }
}

pub fn client() -> reqwest::blocking::Client {
    reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(20))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .expect("HTTP client")
}

/// Polls `check` until it returns Some, or panics after `timeout`.
pub fn wait_for<T>(what: &str, timeout: Duration, mut check: impl FnMut() -> Option<T>) -> T {
    let start = Instant::now();
    loop {
        if let Some(value) = check() {
            return value;
        }
        assert!(start.elapsed() < timeout, "timed out after {timeout:?} waiting for {what}");
        std::thread::sleep(Duration::from_millis(250));
    }
}

/// A unique viewer id for this test process.
pub fn viewer_id(name: &str) -> String {
    let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().subsec_nanos();
    format!("e2e-{name}-{}-{nanos}", std::process::id())
}

/// What a signalling socket received, shared with its reader thread.
#[derive(Default, Debug, Clone)]
pub struct Received {
    pub texts: Vec<String>,
    /// Close code sent by the server, if it closed the socket.
    pub close_code: Option<u16>,
    pub closed: bool,
}

/// One signalling session held open, as a page's WebRTC client opens it
/// (`api/v1/emulator/ws-jsep?viewer=ID`). It counts as one more viewer of
/// the phone while open. Dropping it says `bye` and closes it.
pub struct Viewer {
    pub id: String,
    stop: Arc<AtomicBool>,
    received: Arc<Mutex<Received>>,
    thread: Option<std::thread::JoinHandle<()>>,
}

impl Viewer {
    pub fn open(phone: &CloudPhone, id: &str) -> Viewer {
        let ws_url = phone.ws_url(&format!("api/v1/emulator/ws-jsep?viewer={id}"));
        let (mut socket, _) = tungstenite::connect(ws_url.as_str()).unwrap_or_else(|e| panic!("signalling WebSocket {ws_url}: {e}"));
        if let tungstenite::stream::MaybeTlsStream::Plain(stream) = socket.get_ref() {
            stream.set_read_timeout(Some(Duration::from_millis(300))).unwrap();
        }
        let stop = Arc::new(AtomicBool::new(false));
        let received = Arc::new(Mutex::new(Received::default()));
        let (stop2, received2) = (stop.clone(), received.clone());
        let thread = std::thread::spawn(move || loop {
            if stop2.load(Ordering::SeqCst) {
                let _ = socket.send(Message::Text("{\"bye\":true}".into()));
                let _ = socket.close(None);
                let _ = socket.flush();
                return;
            }
            match socket.read() {
                Ok(Message::Text(text)) => received2.lock().unwrap().texts.push(text.to_string()),
                Ok(Message::Close(frame)) => {
                    let mut r = received2.lock().unwrap();
                    r.close_code = frame.map(|f| u16::from(f.code));
                    r.closed = true;
                    return;
                }
                Ok(_) => {}
                Err(tungstenite::Error::Io(e))
                    if e.kind() == std::io::ErrorKind::WouldBlock || e.kind() == std::io::ErrorKind::TimedOut => {}
                Err(_) => {
                    received2.lock().unwrap().closed = true;
                    return;
                }
            }
        });
        Viewer { id: id.to_string(), stop, received, thread: Some(thread) }
    }

    pub fn received(&self) -> Received {
        self.received.lock().unwrap().clone()
    }

    /// The JSON messages received so far.
    pub fn messages(&self) -> Vec<Value> {
        self.received().texts.iter().filter_map(|t| serde_json::from_str(t).ok()).collect()
    }

    /// Waits for a message accepted by `accept`.
    pub fn wait_message(&self, what: &str, timeout: Duration, accept: impl Fn(&Value) -> bool) -> Value {
        wait_for(what, timeout, || self.messages().into_iter().find(|m| accept(m)))
    }

    /// Says bye and closes now (also done on drop).
    pub fn close(mut self) {
        self.shutdown();
    }

    fn shutdown(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

impl Drop for Viewer {
    fn drop(&mut self) {
        self.shutdown();
    }
}
