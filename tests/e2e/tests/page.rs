//! The page a phone's browser opens.
use cloudphone_e2e::*;

#[test]
fn page_is_served_with_a_fresh_token_and_no_caching() {
    let response = get("");
    assert_eq!(response.status(), 200);
    let headers = response.headers().clone();
    assert_eq!(headers.get("cache-control").map(|v| v.to_str().unwrap()), Some("no-cache"));
    assert_eq!(headers.get("referrer-policy").map(|v| v.to_str().unwrap()), Some("no-referrer"));
    let body = response.text().unwrap();
    assert!(body.contains("<div id=\"root\">") || body.contains("id=\"root\""), "the page has the app's root element");
    assert!(page_token().len() >= 32, "the token is long enough to be unguessable");
}

#[test]
fn page_assets_are_cached_for_good() {
    let body = get("").text().unwrap();
    let start = body.find("/assets/").or_else(|| body.find("assets/")).expect("the page loads assets");
    let rest = &body[start..];
    let end = rest.find('"').expect("end of the asset path");
    let path = rest[..end].trim_start_matches('/');
    let response = get(path);
    assert_eq!(response.status(), 200, "GET {path}");
    let cache = response.headers().get("cache-control").expect("assets carry Cache-Control").to_str().unwrap().to_string();
    assert!(cache.contains("immutable"), "assets are immutable: {cache}");
}
