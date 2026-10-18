//! The page a phone's browser opens.
use cloudphone_e2e::*;

#[test]
fn page_is_served_with_a_fresh_token_and_no_caching() {
    let cp = CloudPhone::start();
    let response = cp.get("");
    assert_eq!(response.status(), 200);
    let headers = response.headers().clone();
    assert_eq!(headers.get("cache-control").map(|v| v.to_str().unwrap()), Some("no-cache"));
    assert_eq!(headers.get("referrer-policy").map(|v| v.to_str().unwrap()), Some("no-referrer"));
    let body = response.text().unwrap();
    assert!(body.contains("id=\"root\""), "the page has the app's root element");
    assert!(cp.page_token().len() >= 32, "the token is long enough to be unguessable");
}

#[test]
fn page_assets_are_cached_for_good() {
    let cp = CloudPhone::start();
    let body = cp.get("").text().unwrap();
    let start = body.find("/assets/").expect("the page loads assets");
    let rest = &body[start..];
    let end = rest.find('"').expect("end of the asset path");
    let path = rest[..end].trim_start_matches('/');
    let response = cp.get(path);
    assert_eq!(response.status(), 200, "GET {path}");
    let cache = response.headers().get("cache-control").expect("assets carry Cache-Control").to_str().unwrap().to_string();
    assert!(cache.contains("immutable"), "assets are immutable: {cache}");
}

#[test]
fn each_gateway_start_draws_a_new_token() {
    let cp = CloudPhone::start();
    let first = cp.page_token();
    cp.fake().action("restart_gateway");
    let second = cp.wait_new_token(&first, std::time::Duration::from_secs(20));
    assert_ne!(first, second);
    // The old token no longer acts on the phone.
    let status = client()
        .post(cp.url("api/v1/emulator/key"))
        .header("X-CloudPhone-Token", &first)
        .json(&serde_json::json!({"key": "GoHome"}))
        .send()
        .unwrap()
        .status();
    assert_eq!(status, 403, "a page loaded before the restart must reload");
}
