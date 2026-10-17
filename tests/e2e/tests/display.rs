//! Android's screen size, set from the page.
use cloudphone_e2e::*;
use serde_json::json;

#[test]
fn display_reports_the_configured_size() {
    let display = get_json("api/v1/display");
    assert!(display["configured"]["width"].as_u64().unwrap() >= 240, "{display}");
    assert!(display["configured"]["height"].as_u64().unwrap() >= 320, "{display}");
}

#[test]
fn invalid_sizes_are_refused_without_restarting_android() {
    for body in [
        json!({"width": 361, "height": 780, "density": 160}),
        json!({"width": 100, "height": 780, "density": 160}),
        json!({"width": 360, "height": 9000, "density": 160}),
        json!({"width": 360}),
    ] {
        let response = post_json("api/v1/display", &body);
        assert_eq!(response.status(), 400, "{body} -> {:?}", response.text());
    }
}
