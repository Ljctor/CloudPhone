//! Only the page itself may act on the phone.
use cloudphone_e2e::*;
use serde_json::json;

fn post_raw(path: &str, token: Option<&str>, origin: Option<&str>) -> u16 {
    let mut request = client().post(url(path)).json(&json!({}));
    if let Some(token) = token {
        request = request.header("X-CloudPhone-Token", token);
    }
    if let Some(origin) = origin {
        request = request.header("Origin", origin);
    }
    request.send().unwrap().status().as_u16()
}

#[test]
fn posts_without_the_page_token_are_refused() {
    assert_eq!(post_raw("api/v1/emulator/key", None, None), 403);
    assert_eq!(post_raw("api/v1/emulator/key", Some("not-the-token"), None), 403);
    assert_eq!(post_raw("api/v1/emulator-settings", None, None), 403);
    assert_eq!(post_raw("api/v1/display", None, None), 403);
}

#[test]
fn other_sites_are_refused_even_with_the_token() {
    let token = page_token();
    assert_eq!(post_raw("api/v1/emulator/key", Some(&token), Some("https://example.org")), 403);
    let status = client().get(url("api/v1/state")).header("Origin", "https://example.org").send().unwrap().status();
    assert_eq!(status, 403);
}

#[test]
fn no_cross_origin_access_is_granted() {
    let response = client().get(url("api/v1/state")).send().unwrap();
    assert!(response.headers().get("access-control-allow-origin").is_none());
}
