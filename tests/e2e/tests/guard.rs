//! Only the page itself may act on the phone.
use cloudphone_e2e::*;
use serde_json::json;
use std::time::Duration;

fn post_raw(cp: &CloudPhone, path: &str, token: Option<&str>, origin: Option<&str>) -> u16 {
    let mut request = client().post(cp.url(path)).json(&json!({"key": "GoHome", "x": 10, "y": 10, "pressed": true}));
    if let Some(token) = token {
        request = request.header("X-CloudPhone-Token", token);
    }
    if let Some(origin) = origin {
        request = request.header("Origin", origin);
    }
    request.send().unwrap().status().as_u16()
}

#[test]
fn posts_without_the_page_token_are_refused_and_reach_nothing() {
    let cp = CloudPhone::start();
    for path in ["api/v1/emulator/key", "api/v1/emulator/touch", "api/v1/emulator-settings", "api/v1/display", "api/v1/viewers/disconnect-others", "api/v1/input"] {
        assert_eq!(post_raw(&cp, path, None, None), 403, "POST {path} without a token");
        assert_eq!(post_raw(&cp, path, Some("not-the-token"), None), 403, "POST {path} with a wrong token");
    }
    std::thread::sleep(Duration::from_millis(500));
    let record = cp.fake().record();
    assert_eq!(record["keys"], json!([]), "no key reached Android");
    assert_eq!(record["touches"], json!([]), "no touch reached Android");
    assert_eq!(record["requests"], json!({"display": [], "settings": []}), "no change was requested");
}

#[test]
fn other_sites_are_refused_even_with_the_token() {
    let cp = CloudPhone::start();
    let token = cp.page_token();
    assert_eq!(post_raw(&cp, "api/v1/emulator/key", Some(&token), Some("https://example.org")), 403);
    let status = client().get(cp.url("api/v1/state")).header("Origin", "https://example.org").send().unwrap().status();
    assert_eq!(status, 403);
    // The same host on another scheme is accepted.
    let own = format!("http://{}", cp.base_url().trim_start_matches("http://").trim_end_matches('/'));
    let status = client().get(cp.url("api/v1/state")).header("Origin", own).send().unwrap().status();
    assert_eq!(status, 200);
}

#[test]
fn no_cross_origin_access_is_granted() {
    let cp = CloudPhone::start();
    let response = client().get(cp.url("api/v1/state")).send().unwrap();
    assert!(response.headers().get("access-control-allow-origin").is_none());
}
