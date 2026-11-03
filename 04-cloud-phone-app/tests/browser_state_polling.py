#!/usr/bin/env python3
"""Opt-in read-only browser checks for state polling and visibility regressions.

Use CLOUDPHONE_URL after deployment, with the same Playwright installation
and executable overrides as browser_reconnect.py. No deployment, Android
input, settings changes or reconnect clicks occur. Temporary viewers and
allowlisted diagnostic uploads are the only expected server-side activity.
Private JSON evidence defaults to /tmp/cloudphone-state-polling-browser.
"""
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright
from browser_reconnect import ALLOWED_POST, INIT, sample

URL = os.environ.get('CLOUDPHONE_URL', '').rstrip('/')
OUT = Path(os.environ.get('CLOUDPHONE_EVIDENCE_DIR', '/tmp/cloudphone-state-polling-browser'))


async def ready(page):
    await page.wait_for_function("""() => {
      const video = document.querySelector('video');
      return video && video.readyState >= 2 && video.videoWidth > 0 && !video.paused;
    }""", timeout=45000)
    evidence = await sample(page)
    assert evidence['peers'] and evidence['peers'][-1]['state'] == 'connected'
    assert evidence['peers'][-1]['decoded'] > 0, 'No decoded video frame'
    return evidence


async def run_browser(kind, playwright):
    executable = os.environ.get('CLOUDPHONE_' + kind.upper() + '_EXECUTABLE')
    browser = await getattr(playwright, kind).launch(headless=True,
        **({'executable_path': executable} if executable else {}),
        **({'args': ['--autoplay-policy=no-user-gesture-required']} if kind == 'chromium' else
           {'firefox_user_prefs': {'media.autoplay.default': 0, 'media.autoplay.blocking_policy': 0}}))
    result = {'browser': kind, 'cases': {}, 'blockedMutations': [], 'resets': [], 'errors': []}

    async def case(name, callback):
        context = await browser.new_context(locale='fr-FR', viewport={'width': 420, 'height': 900})
        await context.add_init_script(INIT)
        faults = {'stateUnavailable': False, 'failedStates': 0, 'healthyPings': 0}

        async def guard(route):
            request = route.request
            path = urlsplit(request.url).path
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                if request.method != 'POST' or path not in ALLOWED_POST:
                    result['blockedMutations'].append({'method': request.method, 'path': path})
                    return await route.abort('blockedbyclient')
                if path.endswith('/reset'):
                    result['resets'].append(name)
            if faults['stateUnavailable'] and path == '/api/v1/state':
                faults['failedStates'] += 1
                return await route.fulfill(status=503, content_type='application/json', body='{}')
            await route.fallback()

        await context.route('**/*', guard)
        page = await context.new_page()
        page.on('pageerror', lambda error: result['errors'].append(str(error)))

        async def response_seen(response):
            if urlsplit(response.url).path == '/api/v1/ping' and response.ok:
                faults['healthyPings'] += 1
        page.on('response', response_seen)
        try:
            await page.goto(URL + '/', wait_until='domcontentloaded')
            before = await ready(page)
            evidence = await callback(page, faults)
            after = await ready(page)
            assert len(after['peers']) == len(before['peers']), 'Unexpected stream replacement'
            assert after['dataSends'] == 0, 'Android data-channel send attempted (blocked)'
            assert not result['blockedMutations'], 'Unexpected HTTP mutation attempted (blocked)'
            assert not result['errors'], 'Browser page error: ' + repr(result['errors'])
            assert name not in result['resets'], 'Read-only scenario triggered a stream reset'
            result['cases'][name] = {'ok': True, 'evidence': evidence, 'before': before, 'after': after}
        except Exception as error:
            result['cases'][name] = {'ok': False, 'error': str(error)}
            try:
                result['cases'][name]['failureSample'] = await sample(page)
            except Exception as sample_error:
                result['cases'][name]['sampleError'] = str(sample_error)
        finally:
            await context.close()
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / (kind + '-state-polling.json')).write_text(json.dumps(result, indent=2))
        print(kind, name, 'PASS' if result['cases'][name]['ok'] else 'FAIL', flush=True)

    async def slow_state(page, _faults):
        await page.evaluate("""() => {
          const originalFetch = window.fetch;
          window.__pollEvidence = {active: 0, max: 0, completed: 0};
          window.fetch = async (...args) => {
            if (!String(args[0]).includes('/api/v1/state?')) return originalFetch(...args);
            const evidence = window.__pollEvidence;
            evidence.active++; evidence.max = Math.max(evidence.max, evidence.active);
            try {
              await new Promise(resolve => setTimeout(resolve, 3400));
              return await originalFetch(...args);
            } finally { evidence.active--; evidence.completed++; }
          };
        }""")
        await page.wait_for_function('window.__pollEvidence.completed >= 2', timeout=20000)
        evidence = await page.evaluate('window.__pollEvidence')
        assert evidence['max'] == 1, 'State polls overlapped: ' + repr(evidence)
        return evidence

    async def unavailable_state(page, faults):
        await page.evaluate("""() => {
          window.__noticeChanges = [];
          const record = () => {
            const texts = [...document.querySelectorAll('[data-cloudphone-notice]')].map(e => e.textContent);
            window.__noticeChanges.push(texts);
          };
          window.__noticeObserver = new MutationObserver(record);
          window.__noticeObserver.observe(document.body, {subtree: true, childList: true, characterData: true});
          record();
        }""")
        faults['healthyPings'] = 0
        faults['stateUnavailable'] = True
        for _ in range(60):
            if faults['failedStates'] >= 2 and faults['healthyPings'] >= 2:
                break
            await page.wait_for_timeout(250)
        assert faults['failedStates'] >= 2 and faults['healthyPings'] >= 2, 'Fault/probe sequence incomplete'
        await page.wait_for_timeout(1000)
        changes = await page.evaluate('window.__noticeChanges')
        assert not any('Serveur injoignable' in text or 'Server unreachable' in text
                       for texts in changes for text in texts), 'Working HTTP ping was classified offline'
        assert await page.locator('[data-cloudphone-notice=cover]').count() == 0, 'Failed state provider covered live video'
        return {'faults': faults.copy(), 'noticeChanges': changes}

    async def visibility(page, _faults):
        await page.evaluate("""() => {
          let hidden = true;
          Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => hidden ? 'hidden' : 'visible'});
          document.dispatchEvent(new Event('visibilitychange'));
          hidden = false;
          document.dispatchEvent(new Event('visibilitychange'));
        }""")
        await page.wait_for_timeout(3000)
        records = (await sample(page))['trace']['records']
        assert not any(record['event'] == 'reset-requested' for record in records), 'Visibility retired a live stream'
        return {'visibilityEvents': [record for record in records if record['event'] == 'page-visibility']}

    try:
        await case('slow_state_responses_are_serialized', slow_state)
        await case('state_failure_with_healthy_http_ping', unavailable_state)
        await case('visibility_preserves_connected_stream', visibility)
    finally:
        await browser.close()
    return all(case['ok'] for case in result['cases'].values()) and not result['blockedMutations'] and not result['resets']


async def main():
    if not URL or urlsplit(URL).scheme not in ('http', 'https'):
        raise SystemExit('Set CLOUDPHONE_URL to the authorized gateway origin after deployment')
    async with async_playwright() as playwright:
        passed = [await run_browser(kind, playwright) for kind in ('chromium', 'firefox')]
    raise SystemExit(0 if all(passed) else 1)


if __name__ == '__main__':
    asyncio.run(main())
