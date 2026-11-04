"""Dated measured rates for an exact accepted farming target.

Only reader completions inside a newly verified farming episode count. Saved
rows are historical snapshots, not live proof; active samples never restore.
No acquisition, OCR, game input, extrapolation or polling of old rate models.
"""
import copy
import hashlib
import json
import math

FARMED = ('mpw18', 'mpw4', 'soul')
# Only these guarded automated actions change the farming configuration or
# an active engraving. Navigation, preview movement/rotation and locks do not.
MUTATIONS = {('stage_select', 'move'), ('battle_settings', 'preset'),
             ('soul_weapon', 'equip'), ('soul_weapon_engraving', 'remove_piece'),
             ('soul_weapon_engraving_preview', 'confirm')}
LABELS = {'gold': 'Gold/h', 'cubes': 'Cubes/h', 'weapon_l3': 'Gear L3/h',
          'accessory_l3': 'Gear L3/h', 'gear_l3': 'Gear L3/h',
          'soul_green': 'Green souls/h', 'soul_blue': 'Blue souls/h', 'soul_red': 'Red souls/h'}


def finite(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def target_of(part):
    if not isinstance(part, dict):
        return None
    stage, preset, weapon = part.get('stage'), part.get('preset'), part.get('soul_weapon')
    if (type(stage) is not int or stage < 1 or preset not in ('I', 'II', 'III', 'IV', 'V')
            or not isinstance(weapon, dict) or type(weapon.get('id')) is not int or weapon['id'] < 1
            or not isinstance(weapon.get('variant'), str) or not weapon['variant']):
        return None
    return {'stage': stage, 'preset': preset,
            'soul_weapon': {'id': weapon['id'], 'variant': weapon['variant']}}


def key_of(mode, target):
    return hashlib.sha256(json.dumps([mode, target], sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def rate_history(ports, rules, modes, loadouts, game, watchdog, table):
    records = {}
    active = None
    generation = 0

    def fields_for(target):
        stage = (target or {}).get('stage')
        drop = None
        if type(stage) is int and 1 <= stage <= len(table['stages']):
            drop = dict(zip(table['fields'], table['stages'][stage - 1])).get('drop')
        gear = {'W': 'weapon_l3', 'A': 'accessory_l3'}.get(drop, 'gear_l3')
        return ('gold', 'cubes', gear, 'soul_green', 'soul_blue', 'soul_red')

    saved = ports.store.saved.get('config_rate_history') or {}
    configs = saved.get('configs') if isinstance(saved, dict) else None
    for key, record in configs.items() if isinstance(configs, dict) else ():
        if not isinstance(record, dict):
            continue
        mode, target = record.get('mode'), target_of(record.get('target'))
        if (mode not in FARMED or not target or key != key_of(mode, target)
                or not isinstance(record.get('revision'), str) or not record['revision']):
            continue
        rates = {}
        stored_rates = record.get('rates')
        for field, row in stored_rates.items() if isinstance(stored_rates, dict) else ():
            if (field in fields_for(target) and isinstance(row, dict)
                    and all(finite(row.get(k)) for k in ('rate_per_hour', 'measured_at', 'window_start', 'window_end', 'span'))
                    and row.get('source') == 'observed_window' and finite(row.get('episode_since'))
                    and row.get('revision') == record.get('revision')
                    and row['rate_per_hour'] >= 0 and 0 <= row['episode_since'] <= row['window_start'] < row['window_end']
                    and row['window_end'] == row['measured_at'] <= ports.clock.wall()
                    and row['span'] == row['window_end'] - row['window_start']):
                rates[field] = copy.deepcopy(row)
        records[key] = {'mode': mode, 'target': target, 'revision': record.get('revision'), 'rates': rates}
    ports.store.register('config_rate_history', lambda: {'version': 1, 'configs': copy.deepcopy(records)})

    def input_mark():
        value = ports.last_input() if callable(getattr(ports, 'last_input', None)) else None
        return copy.deepcopy(value)

    def close(*_args):
        nonlocal active, generation
        active = None
        generation += 1

    if callable(getattr(ports, 'on_relaunch', None)):
        ports.on_relaunch(close)

    def action(event):
        if (event.get('screen'), event.get('move')) in MUTATIONS:
            close()

    ports.on_action(action)

    def current():
        if active is None:
            return None
        state = modes['state']()
        target = target_of(loadouts['loadout'](active['mode']))
        if (not ports.enabled() or state.get('mode') != active['mode'] or state.get('state') not in ('farming', 'moving', 'waiting')
                or state.get('hold') or state.get('mine', {}).get('enabled')
                or modes['mode_epoch']() != active['mode_epoch'] or target != active['target'] or loadouts['revision'](active['mode']) != active['revision']
                or input_mark() != active['input']):
            close()
        if active is not None and (state.get('state') != 'farming' or state.get('tone') != 'ok'):
            watched = watchdog['look']()
            checking = (state.get('state') in ('moving', 'waiting')
                        or watched.get('symptom') in ('verification_due', 'verification_overdue')
                        or watched.get('repairing') in ('loadout', 'stage_change', 'select_preset'))
            if not checking:
                close()
            return None  # Keep samples across a read-only check, not new reads.
        return active

    def verified(receipt):
        nonlocal active
        mode = receipt.get('mode')
        if mode not in FARMED or receipt.get('result') != 'done':
            return
        target = target_of(loadouts['loadout'](mode))
        at = receipt.get('at')
        revision = loadouts['revision'](mode)
        state = modes['state']()
        if (not target or fields_for(target)[2] == 'gear_l3' or receipt.get('target') != target
                or receipt.get('revision', revision) != revision or not finite(at)
                or not 0 <= at <= ports.clock.wall() or not ports.enabled()
                or input_mark() is not None and input_mark().get('wall', float('inf')) > at
                or state.get('mode') != mode or state.get('state') != 'farming'
                or state.get('hold') or state.get('mine', {}).get('enabled') or state.get('tone') != 'ok'):
            return
        proof = (mode, revision, at, generation)
        if active and (active['mode'] == mode and active['target'] == target
                       and active['revision'] == revision and active['input'] == input_mark()
                       and active['mode_epoch'] == modes['mode_epoch']()):
            active['proof'] = proof
            active['accept_after'] = max(active['accept_after'], at)
            return  # Renewal without an intervening mutation keeps sparse samples.
        # A changed target/session, input, launch or mutation starts empty.
        active = {'proof': proof, 'mode': mode, 'target': target, 'revision': revision,
                  'since': at, 'accept_after': at, 'input': input_mark(), 'mode_epoch': modes['mode_epoch'](),
                  'epoch': None, 'place': None,
                  'windows': {field: rules.empty() for field in fields_for(target)}, 'last': {}}

    modes['on_setup_verified'](verified)

    def stage_matches(episode, captured):
        fact = game['facts']().get('stage')
        return bool(fact and fact.get('verified') and fact.get('source') == 'scan'
                    and fact.get('value') == episode['target']['stage']
                    and finite(fact.get('seen')) and episode['since'] <= fact['seen'] <= captured
                    and captured - fact['seen'] <= 30)

    def completed(event):
        episode = current()
        at = event.get('at')
        if (episode is None or not finite(at) or not episode['accept_after'] < at <= ports.clock.wall()
                or type(event.get('epoch')) is not int or event['epoch'] < 0
                or event.get('reader') not in ('gold', 'souls', 'cubes', 'equipment_l3', 'battle_stage', 'badge', 'battle_settings')):
            return
        values = event.get('values') or {}
        if event['reader'] == 'battle_stage':
            if values.get('stage') is not None and values['stage'] != episode['target']['stage']:
                close()
            return
        if event['reader'] in ('badge', 'battle_settings'):
            if values.get('preset') is not None and values['preset'] != episode['target']['preset']:
                close()
            return
        if episode['epoch'] is not None and event.get('epoch') != episode['epoch']:
            close()
            return
        place = (event.get('context') or {}).get('gold_place')
        if not place or place[0] != 'battle' or not place[1] or not stage_matches(episode, at):
            return
        if episode['place'] is not None and not rules.same_place(episode['place'], place[1]):
            close()
            return
        episode['epoch'], episode['place'] = event.get('epoch'), place[1]
        readings = {}
        if event['reader'] == 'gold':
            readings['gold'] = values.get('gold_reading')
        elif event['reader'] == 'souls':
            readings = {'soul_' + colour: value for colour, value in (values.get('souls_reading') or {}).items()
                        if colour in ('green', 'blue', 'red')}
        else:
            for field in fields_for(episode['target']):
                raw = values.get(field)
                raw = raw.get('value') if isinstance(raw, dict) else raw
                if type(raw) is int and raw >= 0:
                    readings[field] = {'value': raw, 'text': str(raw), 'step': 1, 'full': True}
        changed = False
        for field, reading in readings.items():
            if (not reading or not finite(reading.get('value')) or reading['value'] < 0
                    or at <= episode['last'].get(field, float('-inf'))):
                continue
            episode['last'][field] = at
            long = rules.WINDOW if field == 'gold' else rules.RESOURCE_WINDOW
            short = rules.SHORT if field == 'gold' else rules.RESOURCE_WINDOW
            window = rules.counted(episode['windows'][field], reading, at, long,
                                   'skip' if field.startswith('soul_') else 'restart', short=short)
            episode['windows'][field] = window
            seconds = rules.window_for(window['step'], long, short)
            rate, samples = rules.rate(window['samples'], at, seconds)
            if rate is None or not finite(rate * 3600) or len(samples) < 2 or samples[0][0] < episode['since']:
                continue
            key = key_of(episode['mode'], episode['target'])
            record = records.setdefault(key, {'mode': episode['mode'], 'target': episode['target'],
                                              'revision': episode['revision'], 'rates': {}})
            previous = record['rates'].get(field)
            if previous and previous['measured_at'] >= samples[-1][0]:
                continue
            record['rates'][field] = {'rate_per_hour': rate * 3600, 'measured_at': samples[-1][0],
                                      'window_start': samples[0][0], 'window_end': samples[-1][0],
                                      'span': samples[-1][0] - samples[0][0], 'revision': episode['revision'],
                                      'episode_since': episode['since'], 'capture_epoch': episode['epoch'], 'source': 'observed_window'}
            changed = True
        if changed:
            ports.store.save()

    unsubscribe = game['on_read'](completed)

    def response():
        current()  # Polling may invalidate an episode; it never creates data.
        configs = {}
        for mode in (*FARMED, 'free', 'mine'):
            part = loadouts['loadout'](mode) if mode in FARMED else None
            target = target_of(part)
            fields = fields_for(target)
            supported = mode in FARMED and target is not None and fields[2] != 'gear_l3'
            record = records.get(key_of(mode, target), {}) if supported else {}
            rates = record.get('rates', {})
            configs[mode] = {'mode': mode, 'supported': supported,
                             'reason': None if supported else 'mode_not_supported' if mode not in FARMED else 'configuration_incomplete',
                             'revision': loadouts['revision'](mode) if mode in FARMED else None,
                             'target': target if target is not None else copy.deepcopy(part),
                             'fields': [{'field': field, 'label': LABELS[field], 'rate_per_hour': None,
                                         'measured_at': None, 'window_start': None, 'window_end': None,
                                         'span': None, 'source': None, **rates.get(field, {})} for field in fields]}
        return {'version': 1, 'configs': configs}

    async def get(_request):
        return ports.respond(response())

    async def stop(_app):
        unsubscribe()

    return {'routes': [('GET', '/rate-history', get)], 'shutdown': [stop],
            'api': {'get': response}}
