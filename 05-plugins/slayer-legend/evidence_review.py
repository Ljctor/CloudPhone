"""Bounded offline review of archived evidence. Never grants input authority.

Raw captures/graph/feedback remain unchanged; only the separate review ledger
is written. A processed region is visual evidence, not a calibrated reader.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import time
import zlib

VERSION = 1
IDENTITY_VERSION = 2
MAX_PIXELS = 3000000


def png_rgb(data):
    """Read the plugin archive's bounded RGB/RGBA PNG formats with all standard row filters."""
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('not PNG')
    offset, compressed, size = 8, [], None
    while offset + 12 <= len(data):
        length = struct.unpack('>I', data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        body = data[offset + 8:offset + 8 + length]
        if len(body) != length or offset + length + 12 > len(data):
            raise ValueError('truncated PNG')
        crc = struct.unpack('>I', data[offset + 8 + length:offset + 12 + length])[0]
        if zlib.crc32(kind + body) != crc:
            raise ValueError('PNG checksum')
        if kind == b'IHDR':
            width, height, bits, colour, method, filtering, interlace = struct.unpack('>IIBBBBB', body)
            if not 0 < width * height <= MAX_PIXELS or bits != 8 or colour not in (2, 6) or (method, filtering, interlace) != (0, 0, 0):
                raise ValueError('unsupported PNG')
            size = width, height
        elif kind == b'IDAT':
            compressed.append(body)
        elif kind == b'IEND':
            break
        offset += length + 12
    if size is None:
        raise ValueError('PNG dimensions missing')
    width, height = size
    channels = 3 if colour == 2 else 4
    decoder = zlib.decompressobj()
    stride = width * channels + 1
    raw = decoder.decompress(b''.join(compressed), stride * height + 1)
    if len(raw) != stride * height or not decoder.eof or decoder.unused_data:
        raise ValueError('PNG payload size')
    rows, previous = [], bytearray(width * channels)
    for y in range(height):
        filtering = raw[y * stride]
        row = bytearray(raw[y * stride + 1:(y + 1) * stride])
        if filtering not in range(5):
            raise ValueError('PNG filter invalid')
        if filtering:
            for x in range(len(row)):
                left = row[x - channels] if x >= channels else 0
                up = previous[x]
                upper_left = previous[x - channels] if x >= channels else 0
                if filtering == 1:
                    predictor = left
                elif filtering == 2:
                    predictor = up
                elif filtering == 3:
                    predictor = (left + up) // 2
                else:
                    estimate = left + up - upper_left
                    distances = (abs(estimate - left), abs(estimate - up), abs(estimate - upper_left))
                    predictor = (left, up, upper_left)[distances.index(min(distances))]
                row[x] = (row[x] + predictor) % 256
        previous = row
        if channels == 4:
            if any(alpha != 255 for alpha in row[3::4]):
                raise ValueError('capture contains transparency')
            rgb = bytearray(width * 3)
            rgb[0::3], rgb[1::3], rgb[2::3] = row[0::4], row[1::4], row[2::4]
            rows.append(bytes(rgb))
        else:
            rows.append(bytes(row))
    return width, height, b''.join(rows)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as file:
        os.chmod(temporary, 0o600)
        json.dump(value, file, sort_keys=True)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def normal(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1


def geometry(entry):
    kind, tap = entry.get('kind', 'navigation'), entry.get('tap') or {}
    rect = entry.get('rect')
    if rect is not None:
        if not isinstance(rect, list) or len(rect) != 4 or not all(normal(v) for v in rect) or rect[0] >= rect[2] or rect[1] >= rect[3]:
            return None
        return rect
    if kind in ('progression_value', 'resource_value', 'screen_identifier'):
        return None  # These annotations are rectangles, never inferred point marks.
    if not all(normal(tap.get(k)) for k in ('x', 'y')):
        return None
    end = tap.get('end')
    if kind in ('vertical', 'horizontal', 'draggable'):
        if not isinstance(end, dict) or not all(normal(end.get(k)) for k in ('x', 'y')):
            return None
        return [min(tap['x'], end['x']), min(tap['y'], end['y']), max(tap['x'], end['x']), max(tap['y'], end['y'])]
    return [max(0, tap['x'] - .015), max(0, tap['y'] - .015), min(1, tap['x'] + .015), min(1, tap['y'] + .015)]


def identity(scan, tree=None):
    """One deepest registered overlay, independent of detector ordering.

    Sibling/unrelated overlays or an invalid ancestry stay ambiguous. This
    names visual evidence only and never grants navigation authority.
    """
    base = scan.get('screen')
    if base in (None, 'unknown', 'other', 'menu'):
        return None
    tree = tree or {}
    overlays = list(dict.fromkeys(s for s in scan.get('overlays', ())
                                 if isinstance(s, str) and s not in ('panel', 'better_weapon_toast')))
    ancestry = {}
    for name in overlays:
        parents, current = set(), name
        while current:
            if current in parents:
                return None
            parents.add(current)
            # Some calibrated visual overlays are not navigation-tree nodes.
            # The observed base still explicitly parents its own overlay.
            current = (base if current == name and name not in tree and name != base and base in overlays
                       else tree.get(current, {}).get('parent'))
        ancestry[name] = parents
    deepest = [name for name in overlays
               if not any(name in ancestry[other] for other in overlays if other != name)]
    if overlays and len(deepest) != 1:
        return None
    if not overlays and base == 'battle' and 'panel' in scan.get('overlays', ()):
        return None
    screen = deepest[0] if deepest else base
    return 'quest_' + scan['quest_tab'] if screen == 'quest_panel' and scan.get('quest_tab') in ('daily', 'repeat', 'achievement') else screen


def capture_owners(registry):
    """Exact registered examples/variants/scroll captures, never filename guesses."""
    owners = {}
    for section in ('screens', 'tree'):
        for screen, node in registry.get(section, {}).items():
            paths = [node.get('example')] + node.get('variants', [])
            for scroll in node.get('scroll', []):
                paths.extend(scroll.get('captures', []))
            for path in paths:
                if isinstance(path, str) and path.endswith('.png'):
                    owners.setdefault(Path(path).stem, set()).add(screen)
    return owners


def match_move(entry, source, target, navigation, tree=None):
    tap = entry.get('tap') or {}
    tree = tree or {}
    source_panel = tree.get(source, {}).get('screen', source)
    # A child tab must name the exact existing physical-panel move. A shared
    # destination panel alone cannot establish which tab was selected.
    target_node = tree.get(target, {})
    target_panel = target_node.get('screen', target)
    target_via = target_node.get('via') if target_panel != target else None
    if target_panel != target and not target_via:
        return None
    for move in navigation.get('screens', {}).get(source_panel, {}).get('moves', []):
        if target_via and target_via != source_panel + '/' + move.get('id', ''):
            continue
        if move.get('forbidden') or move.get('assumed') or move.get('to') != target_panel:
            continue
        point = move.get('tap')
        if point and tap.get('kind', 'tap') == 'tap' and all(normal(tap.get(k)) for k in ('x', 'y')):
            if abs(point[0] - tap['x']) <= navigation.get('tolerance', .03) and abs(point[1] - tap['y']) <= navigation.get('tolerance', .03):
                return move['id']
    return None


def graph_reviews(graph):
    """Audit every passive observation without inventing missing RGB evidence."""
    nodes = {node.get('id'): node for node in graph.get('nodes', []) if isinstance(node, dict)}
    reviews, signatures = {}, {}
    for index, edge in enumerate(graph.get('edges', [])):
        edge_id = 'trace-edge:' + str(index)
        valid = (isinstance(edge, dict) and edge.get('from') in nodes and edge.get('to') in nodes
                 and edge.get('kind') in ('tap', 'long', 'swipe')
                 and normal(edge.get('x')) and normal(edge.get('y')))
        if valid and edge['kind'] == 'swipe':
            valid = normal(edge.get('x2')) and normal(edge.get('y2'))
        result = {'status': 'ambiguous' if valid else 'rejected',
                  'reason': 'source_capture_missing_for_navigation_validation' if valid else 'graph_geometry_or_reference_invalid',
                  'gesture_authority': False}
        if valid:
            signature = tuple(edge.get(k) for k in ('from', 'to', 'kind', 'x', 'y', 'x2', 'y2'))
            if signature in signatures:
                result['duplicate_of'] = signatures[signature]
            else:
                signatures[signature] = edge_id
        reviews[edge_id] = result
    return reviews


def revision(plugin):
    files = [p for p in plugin.glob('*.py') if not p.name.startswith('test_')] + list(plugin.glob('*.json')) + list((plugin / 'fixtures').glob('*.txt'))
    return digest(str(IDENTITY_VERSION).encode() + b''.join(str(p.relative_to(plugin)).encode() + p.read_bytes() for p in sorted(files)))


def batch(data, plugin, screens, limit=16, ledger=None, feedback_file=None):
    """Review at most limit changed items, retaining unresolved evidence."""
    data, plugin = Path(data), Path(plugin)
    navigation = read_json(plugin / 'navigation.json', {})
    registry = read_json(plugin / 'screen_registry.json', {})
    tree = getattr(screens, 'TREE', None) or registry.get('tree', {})
    owners = capture_owners(registry)
    current = ledger or {'version': VERSION, 'items': {}, 'images': {}}
    rev = revision(plugin)
    if current.get('reader_revision') != rev:
        current = {'version': VERSION, 'items': {}, 'images': {}, 'reader_revision': rev}
    manual = data / 'manual-clicks'
    paths = sorted(manual.glob('*.json'))
    paths += sorted((data / 'screenshots').glob('*.png'))
    processed = 0
    image_cache = current['images']
    def inspect(path, node):
        if not path.is_file():
            return {'nodeId': node, 'status': 'rejected', 'reason': 'image_missing'}
        raw = path.read_bytes()
        sha = digest(raw)
        if sha not in image_cache:
            try:
                shot = png_rgb(raw)
                scan = screens.look(shot)
                screen = identity(scan, tree)
                image_cache[sha] = {'screen': screen, 'status': 'processed' if screen else 'ambiguous',
                                    'reason': 'current_calibrated_reader' if screen else 'screen_not_recognised',
                                    'scan': {k: scan[k] for k in ('screen', 'overlays', 'plain', 'quest_tab') if k in scan}}
            except Exception as error:
                image_cache[sha] = {'screen': None, 'status': 'rejected', 'reason': 'image_or_reader_error', 'error_type': type(error).__name__}
        return {**image_cache[sha], 'sha256': sha, 'nodeId': node}
    for path in paths:
        example = path.suffix == '.png'
        key = 'example:' + path.stem if example else 'manual:' + path.stem
        payload = path.read_bytes()
        source = digest(payload + b''.join(p.read_bytes() for p in (manual / (path.stem + '-before.png'), manual / (path.stem + '-after.png')) if p.is_file())) if not example else digest(payload)
        if current['items'].get(key, {}).get('source_sha256') == source:
            continue
        if processed >= limit:
            break
        processed += 1
        if example:
            result = inspect(path, key)
            item = {'nodeId': key, 'kind': 'screen_example', 'status': result['status'], 'reason': result['reason'], 'before': result}
            if result.get('screen') and result['screen'] != path.stem and result['screen'] not in owners.get(path.stem, set()):
                item.update(status='ambiguous', reason='archived_label_disagrees_with_current_reader')
        else:
            entry = read_json(path, None)
            item = {'captureId': path.stem, 'kind': (entry or {}).get('kind', 'navigation')}
            for side in ('before', 'after'):
                image = manual / (path.stem + '-' + side + '.png')
                if image.is_file():
                    item[side] = inspect(image, key + ':' + side)
            if not isinstance(entry, dict):
                item.update(status='rejected', reason='metadata_invalid')
            elif entry.get('capture_status') not in (None, 'complete'):
                item.update(status='rejected', reason='capture_' + str(entry.get('capture_status')))
            else:
                before = inspect(manual / (path.stem + '-before.png'), key + ':before')
                item['before'] = before
                item.update(status=before['status'], reason=before['reason'])
                if item['kind'] == 'navigation':
                    after = inspect(manual / (path.stem + '-after.png'), key + ':after')
                    item['after'] = after
                    move = match_move(entry, before.get('screen'), after.get('screen'), navigation, tree)
                    if before['status'] == after['status'] == 'processed' and move and entry.get('after_stable') is True:
                        item.update(status='processed', reason='existing_validated_navigation_match', moveId=move)
                    else:
                        item.update(status='ambiguous', reason='navigation_not_proven_by_existing_map')
                elif item['kind'] not in ('screen', 'screen_correction'):
                    rect = geometry(entry)
                    if rect is None:
                        item.update(status='rejected', reason='geometry_invalid')
                    elif before['status'] == 'processed':
                        item['annotation'] = {'id': key, 'screen': before['screen'], 'kind': item['kind'], 'rect': rect,
                                              'forbidden': item['kind'] == 'forbidden' or item['kind'] == 'action' and entry.get('forbidden') is True, 'source': 'reviewed_user_evidence',
                                              'side': 'before', 'review_status': 'processed', 'nodeId': key + ':before',
                                              'gesture_authority': False, 'reader_calibrated': False}
                        item.update(status='processed', reason='read_only_annotation_integrated')
                expected = entry.get('expected_screen')
                if expected and expected != before.get('screen'):
                    item.update(status='ambiguous', reason='reported_screen_conflicts_with_current_reader', expected_screen=expected)
        item['source_sha256'] = source
        item['reviewed_at'] = time.time()
        current['items'][key] = item
    current['updated_at'] = time.time()
    current['summary'] = {status: sum(item['status'] == status for item in current['items'].values()) for status in ('processed', 'ambiguous', 'rejected')}
    current['summary'].update(total=len(paths), reviewed=len(current['items']), pending=max(0, len(paths) - len(current['items'])), unique_images=len(image_cache))
    current['annotations'] = [item['annotation'] for item in current['items'].values() if item['status'] == 'processed' and 'annotation' in item]
    graph = read_json(data / 'trace.json', {})
    current['graph'] = {'nodes': len(graph.get('nodes', [])), 'edges': len(graph.get('edges', [])),
                        'taps': sum(e.get('count', 0) for e in graph.get('edges', [])),
                        'status': 'ambiguous', 'reason': 'passive_graph_has_lossy_thumbnails_without_source_captures',
                        'gesture_authority': False, 'edge_reviews': graph_reviews(graph)}
    feedback = read_json(feedback_file or data / 'review-feedback.json', {}).get('items', [])
    nodes = {side.get('nodeId'): side for item in current['items'].values()
             for side in (item.get('before', {}), item.get('after', {})) if side.get('nodeId')}
    current['feedback'] = {}
    for report in feedback:
        if not isinstance(report, dict) or not isinstance(report.get('id'), str):
            continue
        node = nodes.get(report.get('nodeId'))
        expected = report.get('correctScreen')
        status, reason = 'ambiguous', 'feedback_requires_reader_or_geometry_validation'
        if node and expected and expected == node.get('screen') and node.get('status') == 'processed':
            status, reason = 'processed', 'current_reader_confirms_reported_identity'
        elif str(report.get('nodeId', '')).startswith('trace:'):
            reason = 'passive_thumbnail_cannot_validate_reported_identity'
        elif str(report.get('nodeId', '')).startswith('screen:') and str(report['nodeId'])[7:] in navigation.get('screens', {}):
            reason = 'configured_identity_or_route_requires_validation'
        elif node is None:
            status, reason = 'rejected', 'feedback_target_not_found'
        current['feedback'][report['id']] = {'nodeId': report.get('nodeId'), 'status': status,
                                            'reason': reason, 'correctScreen': expected,
                                            'gesture_authority': False}
    return current, processed


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir', required=True)
    p.add_argument('--plugin-dir', default=str(Path(__file__).parent))
    p.add_argument('--ledger', required=True)
    p.add_argument('--batch-size', type=int, default=16)
    p.add_argument('--feedback-file')
    p.add_argument('--once', action='store_true', help='process one bounded batch and return')
    args = p.parse_args()
    plugin = Path(args.plugin_dir)
    spec = importlib.util.spec_from_file_location('reviewed_screens', plugin / 'screens.py')
    screens = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(screens)
    ledger = read_json(args.ledger, None)
    while True:
        ledger, count = batch(args.data_dir, plugin, screens, max(1, min(args.batch_size, 32)), ledger, args.feedback_file)
        atomic_json(args.ledger, ledger)
        print(json.dumps(ledger['summary']), flush=True)
        if args.once or not count:
            break


if __name__ == '__main__':
    main()
