#!/usr/bin/env bash
# Read-only HTTP validation of the standalone private review catalogue.
set -euo pipefail
base=${1:?Usage: verify.sh http://PRIVATE_ADDRESS:7890}
python3 - "$base" <<'PY'
import json
import sys
import urllib.error
import urllib.request

base = sys.argv[1].rstrip('/')
def request(path, expected=200, **kwargs):
    try:
        response = urllib.request.urlopen(urllib.request.Request(base + path, **kwargs), timeout=15)
    except urllib.error.HTTPError as error:
        assert error.code == expected, (path, error.code, expected)
        return None
    assert response.status == expected, (path, response.status, expected)
    assert response.headers.get('Cache-Control') == 'private, no-store'
    return response.read()

assert b'<!doctype html' in request('/').lower()
graph = json.loads(request('/api/graph'))
assert graph['version'] == 1
nodes = {node['id']: node for node in graph['nodes']}
for node in nodes.values():
    assert {'id', 'screen', 'label', 'image', 'regions', 'source'} <= node.keys()
    if node['source'] == 'trace':
        assert node['image'] is None
for edge in graph['edges']:
    assert edge['from'] in nodes and edge['to'] in nodes
    assert edge['kind'] in ('tap', 'long', 'swipe')
    assert all(0 <= edge['start'][axis] <= 1 for axis in ('x', 'y'))
assert isinstance(json.loads(request('/api/feedback'))['items'], list)
request('/review_server.py', 404)
request('/api/image/example:missing-image', 404)
# Invalid empty objects cannot create feedback even if a guard regresses.
request('/api/feedback', 403, data=b'{}', headers={'Content-Type': 'application/json', 'Origin': 'https://external.invalid'})
request('/api/feedback', 415, data=b'{}', headers={'Content-Type': 'text/plain'})
print('Private passive review HTTP contract: OK')
print(json.dumps(graph['stats'], sort_keys=True))
PY
