//! Poll ordering and page visibility must not manufacture connection outages.
use cloudphone_e2e::browser::{browser_test, Options};
use cloudphone_e2e::*;
use std::time::Duration;

#[test]
fn slow_state_responses_never_overlap() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::default(), |page| async move {
        page.js("const nativeFetch = window.fetch; window.pollEvidence = {active: 0, max: 0, completed: 0}; \
            window.fetch = async (...args) => { \
              if (!String(args[0]).includes('/api/v1/state?')) return nativeFetch(...args); \
              const evidence = window.pollEvidence; evidence.active++; evidence.max = Math.max(evidence.max, evidence.active); \
              try { await new Promise(resolve => setTimeout(resolve, 3400)); return await nativeFetch(...args); } \
              finally { evidence.active--; evidence.completed++; } \
            }", vec![]).await;
        page.wait_js("two slow state polls completed", Duration::from_secs(18),
            "return window.pollEvidence.completed >= 2 ? window.pollEvidence : null", vec![]).await;
        let evidence = page.js("return window.pollEvidence", vec![]).await;
        assert_eq!(evidence["max"], 1, "state responses must stay ordered: {evidence}");
    });
}

#[test]
fn a_failed_state_provider_with_a_working_ping_is_not_an_offline_gateway() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::default(), |page| async move {
        page.js("const nativeFetch = window.fetch; window.failedStates = 0; window.reachablePings = 0; \
            window.fetch = async (...args) => { \
              const url = String(args[0]); \
              if (url.includes('/api/v1/state?')) { window.failedStates++; return new Response('{}', {status: 503}); } \
              const response = await nativeFetch(...args); \
              if (url.endsWith('/api/v1/ping') && response.ok) window.reachablePings++; \
              return response; \
            }", vec![]).await;
        page.wait_js("two failed state polls and successful reachability probes", Duration::from_secs(12),
            "return window.failedStates >= 2 && window.reachablePings >= 2 ? true : null", vec![]).await;
        let banners = page.banners().await;
        assert!(!banners.iter().any(|text| text.contains("Serveur injoignable") || text.contains("Server unreachable")),
            "state failure must not override successful HTTP reachability: {banners:?}");
    });
}

#[test]
fn showing_a_connected_page_keeps_its_live_stream() {
    let cp = CloudPhone::start();
    browser_test(&cp, Options::default(), |page| async move {
        let before = page.js("return window.cloudphoneDiagnostics.snapshot().records.filter(r => r.event === 'session-start').length", vec![]).await;
        page.js("let hidden = true; Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => hidden ? 'hidden' : 'visible'}); \
            document.dispatchEvent(new Event('visibilitychange')); hidden = false; document.dispatchEvent(new Event('visibilitychange'))", vec![]).await;
        page.sleep(Duration::from_secs(2)).await;
        let after = page.js("return window.cloudphoneDiagnostics.snapshot().records.filter(r => r.event === 'session-start').length", vec![]).await;
        assert_eq!(before, after, "visibility must not tear down a decoded live stream");
    });
}
