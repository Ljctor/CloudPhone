//! Black-box helpers for end-to-end tests of a running Cloud Phone instance.
//!
//! The tests only know what a user's browser can reach: the page and its
//! HTTP API at `CLOUDPHONE_URL` (for example `http://10.20.0.1:8000/`, or a
//! local SSH tunnel to it). They never read the application's code or the
//! server's files. Tests that restart Android are marked `#[ignore]` and run
//! only with `cargo test -- --ignored`.

use serde_json::Value;
use std::time::{Duration, Instant};

/// Base URL of the instance under test, always ending with "/".
pub fn base_url() -> String {
    let url = std::env::var("CLOUDPHONE_URL").expect(
        "set CLOUDPHONE_URL to the page of the instance under test, e.g. http://10.20.0.1:8000/",
    );
    if url.ends_with('/') { url } else { format!("{url}/") }
}

pub fn client() -> reqwest::blocking::Client {
    reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(20))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .expect("HTTP client")
}

pub fn url(path: &str) -> String {
    format!("{}{}", base_url(), path.trim_start_matches('/'))
}

pub fn get(path: &str) -> reqwest::blocking::Response {
    client().get(url(path)).send().unwrap_or_else(|e| panic!("GET {path}: {e}"))
}

pub fn get_json(path: &str) -> Value {
    let response = get(path);
    assert!(response.status().is_success(), "GET {path}: HTTP {}", response.status());
    response.json().unwrap_or_else(|e| panic!("GET {path}: not JSON: {e}"))
}

/// The per-start token the page carries in `<meta name="cloudphone-token">`,
/// as a browser would read it.
pub fn page_token() -> String {
    let page = get("").text().expect("page body");
    let marker = "name=\"cloudphone-token\" content=\"";
    let start = page.find(marker).expect("the page carries a cloudphone-token meta tag") + marker.len();
    let end = page[start..].find('"').expect("closing quote of the token") + start;
    page[start..end].to_string()
}

/// POST as the page does: JSON body and the page's token.
pub fn post_json(path: &str, body: &Value) -> reqwest::blocking::Response {
    client()
        .post(url(path))
        .header("X-CloudPhone-Token", page_token())
        .json(body)
        .send()
        .unwrap_or_else(|e| panic!("POST {path}: {e}"))
}

/// Polls `check` until it returns Some, or panics after `timeout`.
pub fn wait_for<T>(what: &str, timeout: Duration, mut check: impl FnMut() -> Option<T>) -> T {
    let start = Instant::now();
    loop {
        if let Some(value) = check() {
            return value;
        }
        assert!(start.elapsed() < timeout, "timed out after {timeout:?} waiting for {what}");
        std::thread::sleep(Duration::from_secs(3));
    }
}

/// Waits until the server reports Android booted and answering.
pub fn wait_for_android(timeout: Duration) {
    wait_for("Android to boot", timeout, || {
        let response = client().get(url("api/v1/state")).send().ok()?;
        let state: Value = response.json().ok()?;
        (state["android"]["booted"] == Value::Bool(true)).then_some(())
    });
}
