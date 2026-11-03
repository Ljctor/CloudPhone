#!/usr/bin/env python3
"""Opt-in real-browser reconnect check; never sends Android input or settings.

Requires Playwright Python and installed Chromium/Firefox browsers. Set
CLOUDPHONE_URL to the gateway origin; optional CLOUDPHONE_EVIDENCE_DIR chooses
private JSON evidence (default /tmp/cloudphone-reconnect-browser). This creates
only temporary viewers, their reconnect requests and diagnostic events. All
other HTTP mutations and all WebRTC data-channel sends are blocked locally.
Run after deployment; this script does not deploy or restart any service.
"""
import asyncio
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

URL = os.environ.get("CLOUDPHONE_URL", "").rstrip("/")
OUT = Path(os.environ.get("CLOUDPHONE_EVIDENCE_DIR", "/tmp/cloudphone-reconnect-browser"))
ALLOWED_POST = {"/api/v1/stream/reset", "/api/v1/viewers/reset", "/api/v1/stream-diagnostics/events"}
INIT = r"""(() => {
  window.__testPeers = []; window.__testTracks = []; window.__testDataSends = 0; window.__testBlockedAttempts = [];
  const NativePeer = window.RTCPeerConnection;
  window.RTCPeerConnection = new Proxy(NativePeer, {construct(target, args) {
    const peer = new target(...args); window.__testPeers.push(peer);
    peer.addEventListener('track', e => window.__testTracks.push(e.track));
    return peer;
  }});
  RTCDataChannel.prototype.send = function() { window.__testDataSends++; throw Error('Test forbids Android data-channel input'); };
  const NativeSocket = window.WebSocket;
  window.WebSocket = new Proxy(NativeSocket, {construct(target, args) {
    if (window.__testBlockSignaling && String(args[0]).includes('/ws-jsep')) {
      window.__testBlockedAttempts.push(new URL(args[0]).searchParams.get('attempt'));
      throw new DOMException('Test blocks signaling before server', 'SecurityError');
    }
    return new target(...args);
  }});
})();"""

async def sample(page):
    return await page.evaluate("""async () => {
      const v = document.querySelector('video');
      const peers = await Promise.all(window.__testPeers.map(async p => {
        let decoded = 0; const inbound = [];
        for (const s of (await p.getStats()).values()) if(s.type === 'inbound-rtp' && (s.kind === 'video' || s.mediaType === 'video')) {
          decoded += s.framesDecoded || 0;
          inbound.push({framesDecoded:s.framesDecoded,framesReceived:s.framesReceived,bytesReceived:s.bytesReceived});
        }
        return {state:p.connectionState, signaling:p.signalingState, decoded, inbound};
      }));
      return {video:v && {ready:v.readyState,width:v.videoWidth,height:v.videoHeight,paused:v.paused,time:v.currentTime},
        peers, tracks:window.__testTracks.map(t=>({kind:t.kind,state:t.readyState})), dataSends:window.__testDataSends,
        trace:window.cloudphoneDiagnostics?.snapshot()};
    }""")

async def advancing(page):
    await page.wait_for_function("""() => {const v=document.querySelector('video'); return v && v.readyState>=2 && v.videoWidth>0 && !v.paused;}""", timeout=45000)
    before = await sample(page)
    for _ in range(40):
        await page.wait_for_timeout(250)
        after = await sample(page)
        if (sum(p['decoded'] for p in after['peers']) > sum(p['decoded'] for p in before['peers'])
                and after['video']['time'] > before['video']['time']):
            assert after['dataSends'] == 0
            return after
    raise AssertionError('No decoded-frame and media-time advancement')

async def run_browser(kind, playwright):
    executable = os.environ.get('CLOUDPHONE_' + kind.upper() + '_EXECUTABLE')
    browser = await getattr(playwright, kind).launch(headless=True,
        **({'executable_path':executable} if executable else {}),
        **({'args':['--autoplay-policy=no-user-gesture-required']} if kind == 'chromium' else
           {'firefox_user_prefs':{'media.autoplay.default':0, 'media.autoplay.blocking_policy':0}}))
    result = {'browser':kind, 'cases':{}, 'blockedMutations':[], 'telemetryResponses':[], 'errors':[]}
    contexts = []
    async def make_page(block=False, stale=False):
        context = await browser.new_context(locale='fr-FR', viewport={'width':420,'height':900})
        contexts.append(context)
        await context.add_init_script(INIT + ('\nwindow.__testBlockSignaling = true;' if block else ''))
        if stale:
            # Change only the HTML token received by this temporary browser.
            async def stale_html(route):
                response = await route.fetch()
                body = await response.text()
                body, count = re.subn(r'(<meta[^>]*name=["\']cloudphone-token["\'][^>]*content=["\'])[^"\']*', r'\g<1>deliberately-stale-browser-test-token', body)
                assert count == 1, 'Token meta element not found'
                await route.fulfill(response=response, body=body)
            await context.route(re.compile(r'.*/(?:\?.*)?$'), stale_html)
        async def guard(route):
            request = route.request
            path = urlsplit(request.url).path
            if request.method not in ('GET','HEAD','OPTIONS') and not (request.method == 'POST' and path in ALLOWED_POST):
                result['blockedMutations'].append({'method':request.method,'path':path})
                await route.abort('blockedbyclient')
            else:
                await route.fallback()
        await context.route('**/*', guard)
        page = await context.new_page()
        page.on('pageerror', lambda e: result['errors'].append(str(e)))
        async def response_seen(response):
            if urlsplit(response.url).path in ALLOWED_POST:
                result['telemetryResponses'].append({'path':urlsplit(response.url).path,'status':response.status})
        page.on('response', response_seen)
        await page.goto(URL+'/', wait_until='domcontentloaded')
        return page
    async def case(name, callback):
        previous_contexts = len(contexts)
        try:
            result['cases'][name] = {'ok':True, 'evidence':await callback()}
        except Exception as e:
            result['cases'][name] = {'ok':False,'error':str(e)}
        finally:
            for context in contexts[previous_contexts:]:
                for page in context.pages:
                    if await page.evaluate('window.__testDataSends || 0'):
                        result['safetyFailure'] = 'Android data-channel send attempted (blocked)'
                await context.close()
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT/(kind+'.json')).write_text(json.dumps(result,indent=2))
        print(kind, name, 'PASS' if result['cases'][name]['ok'] else 'FAIL', flush=True)
    async def reconnects():
        page = await make_page()
        first = await advancing(page)
        other = await make_page()
        await advancing(other)
        evidence = {'initial':first,'reconnects':[]}
        for index in range(2):
            previous_count = await page.evaluate('window.__testPeers.length')
            other_count = await other.evaluate('window.__testPeers.length')
            await page.get_by_role('button',name=re.compile('Reconnecter la vidéo|Reconnect the video')).last.click()
            await page.wait_for_function('(n)=>window.__testPeers.length===n+1',arg=previous_count,timeout=45000)
            current = await advancing(page)
            assert all(p['state']=='closed' and p['signaling']=='closed' for p in current['peers'][:-1]), 'Old peer still open'
            assert all(t['state']=='ended' for t in current['tracks'][:-1]), 'Old track still live'
            unaffected = await advancing(other)
            assert len(unaffected['peers']) == other_count, 'Second viewer replaced its peer'
            assert unaffected['peers'][-1]['state']=='connected', 'Second viewer disconnected'
            evidence['reconnects'].append({'own':current,'other':unaffected})
        await page.context.close(); await other.context.close()
        return evidence
    async def stale_token():
        page = await make_page(stale=True)
        await advancing(page)
        # Ensure the reset itself receives a stale token even if telemetry has
        # already refreshed the stale HTML token while the first frame arrived.
        await page.evaluate("document.querySelector('meta[name=cloudphone-token]').content='deliberately-stale-browser-test-token'")
        count = await page.evaluate('window.__testPeers.length')
        await page.get_by_role('button',name=re.compile('Reconnecter la vidéo|Reconnect the video')).last.click()
        await page.wait_for_function('(n)=>window.__testPeers.length===n+1',arg=count,timeout=45000)
        current = await advancing(page)
        events = [r['event'] for r in current['trace']['records']]
        assert 'token-refused' in events and 'token-refreshed' in events, 'Token refresh evidence absent'
        assert await page.evaluate("document.querySelector('meta[name=cloudphone-token]').content !== 'deliberately-stale-browser-test-token'")
        await page.context.close()
        return current
    async def blocked_options():
        page = await make_page(block=True)
        await page.wait_for_function("window.cloudphoneDiagnostics?.snapshot().records.some(r=>r.event==='websocket-constructor-error')",timeout=20000)
        await page.get_by_role('button',name='Options',exact=True).first.click()
        dialog = page.get_by_role('dialog',name='Options',exact=True)
        await dialog.wait_for(state='visible')
        select = dialog.locator('select').first
        assert await select.is_enabled(), 'Options language selector disabled'
        await select.click()  # Opens native options; never changes the value.
        await select.press('Escape')
        assert await dialog.locator('input[type=checkbox]').first.is_enabled()
        # Check actual hit testing so an invisible input layer cannot cover it.
        assert await select.evaluate("e=>{const r=e.getBoundingClientRect();const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return hit===e||e.contains(hit)}"), 'Options covered by another layer'
        await page.wait_for_timeout(1800)
        current = await sample(page)
        assert not current['peers'], 'Blocked attempt unexpectedly created peer'
        assert not any(r['event']=='websocket-open' for r in current['trace']['records'])
        snapshot = await (await page.request.get(URL+'/api/v1/stream-diagnostics')).json()
        blocked_ids = await page.evaluate('window.__testBlockedAttempts')
        attempts = [a for a in snapshot.get('attempts',[]) if a.get('attempt_id') in blocked_ids and not a.get('session_ids') and any(e.get('kind')=='websocket' and e.get('state')=='constructor-error' for e in a.get('browser_events',[]))]
        assert attempts, 'Pre-session failed attempt missing from gateway telemetry'
        current['serverAttempts'] = attempts
        await page.context.close()
        return current
    try:
        await case('reconnect_twice_second_viewer', reconnects)
        await case('stale_token_refresh', stale_token)
        await case('blocked_signaling_options_and_attempt_telemetry', blocked_options)
        assert not result['blockedMutations'], 'Unexpected mutation attempted: '+repr(result['blockedMutations'])
    except Exception as e:
        result['safetyFailure'] = str(e)
    finally:
        await browser.close()
        (OUT/(kind+'.json')).write_text(json.dumps(result,indent=2))
    return all(c['ok'] for c in result['cases'].values()) and not result.get('safetyFailure')

async def main():
    if not URL or urlsplit(URL).scheme not in ('http','https'):
        raise SystemExit('Set CLOUDPHONE_URL to the authorized gateway origin')
    async with async_playwright() as playwright:
        passed = []
        for kind in ('chromium','firefox'):
            passed.append(await run_browser(kind,playwright))
        raise SystemExit(0 if all(passed) else 1)

if __name__ == '__main__':
    asyncio.run(main())
