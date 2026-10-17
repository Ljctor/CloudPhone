//! The optional game helper: where to hide the emerald decimals.
use cloudphone_e2e::*;

#[test]
fn emerald_mask_answers_with_a_mask_or_a_reason() {
    let answer = get_json("api/v1/emerald-mask");
    if answer["mask"].is_null() {
        assert!(answer["reason"].is_string(), "{answer}");
    } else {
        let mask = &answer["mask"];
        for key in ["x", "y", "width", "height"] {
            assert!(mask[key].as_f64().unwrap() >= 0.0, "{answer}");
        }
        assert!(mask["color"].as_str().unwrap().starts_with("rgb("), "{answer}");
    }
}
