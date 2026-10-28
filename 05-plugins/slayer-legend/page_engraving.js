// Edit a draft, then explicitly apply one complete target to the gateway.
// Accepted configuration and observed in-game equipment are separate facts.

import { withDeadline } from './page_request_deadline.js';
const PRESETS = ['I', 'II', 'III', 'IV', 'V'];
const FIELDS = ['Stage', 'Preset', 'Weapon', 'Variant'];
// The sheet's piece colours as CSS colours; the gold variants' pieces
// have none and take these in turn.
const FILLS = { red: '#e0453a', blue: '#3b82f6', purple: '#9b5de5', green: '#3fb950', yellow: '#f2c230' };
const TURN = ['#e0453a', '#3b82f6', '#9b5de5', '#3fb950', '#f2c230', '#f08c2e', '#8b5a2b'];
// The weapons' soul colours.
const DOTS = { green: '🟢', blue: '🔵', red: '🔴' };

const ENGLISH = {
  'Réessayer cette configuration': 'Retry this configuration',
  'Recharger la cible': 'Reload target',
  'Soul Weapon et gravure vérifiées · huit cartes verrouillées': 'Soul Weapon and engraving verified · eight cards locked',
  'Configuration vérifiée': 'Configuration verified',
  "Configuration demandée non vérifiée": "Requested configuration unverified",
  "Cible": "Target",
  "Acceptée": "Accepted",
  "Dernière tentative : {weapon} · arme et gravure à vérifier": "Last attempt: {weapon} · weapon and engraving need checking",
  "Aucune preuve enregistrée pour cette cible": "No recorded evidence for this target",
  "Cible différente sur le serveur · vérifier avant d’appliquer": "Server target differs \u00b7 review before applying",
  "Configuration modifiée ailleurs : recharge la cible avant d’appliquer": "Configuration changed elsewhere: reload the target before applying",
  "Dernier contrôle : autre arme ou gravure · cible acceptée à vérifier": "Last observation: another target \u00b7 accepted target unverified",
  "Gravure automatique désactivée · premier passage soumis à supervision": "Automatic engraving disabled · first execution requires supervision",
  "Gravure et verrouillage des huit cartes vérifiés le {time} · contrôle actuel à refaire": "Grid and locks verified at {time} \u00b7 historical evidence, current equipment unconfirmed",
  "Remise en sécurité nécessaire : les huit cartes ne sont pas confirmées verrouillées": "Lock recovery required \u00b7 target unverified",
  "Changement automatique de Soul Weapon désactivé": "Automatic Soul Weapon changes disabled",
  "Tentative enregistrée le {time} · arme et gravure à vérifier": "Attempt recorded at {time} \u00b7 target unverified",
  "Huit cartes revérifiées verrouillées le {time} · gravure demandée non vérifiée": "Locks rechecked at {time} \u00b7 complete grid unverified",

  'Préréglage de combat': 'Battle settings preset',
  'Soul Weapon': 'Soul Weapon',
  'Gravure': 'Engraving',
  'Grille': 'Grid',
  'Attention': 'Warning',
  'Grille à vérifier en jeu avant la pose': 'Grid to check in game before placing',
  'gateway injoignable': 'gateway unreachable',
  "Sans Soul Weapon demandée": "No Soul Weapon requested",
  "Cible acceptée indisponible": "Accepted target unavailable",
  "Configuration du serveur indisponible": "Server configuration unavailable",
  "Choisir un stage valide": "Choose a valid stage",
  "Choisir un préréglage de combat": "Choose a battle preset",
  "Choisir une gravure valide pour cette arme": "Choose a valid engraving for this weapon",
  "Enregistrement de la cible…": "Submitting target\u2026",
  "Application non confirmée": "Application unconfirmed",
  "Cible acceptée · équipement en jeu à vérifier": "Target accepted \u00b7 in-game equipment awaiting verification",
  "Modifications non appliquées": "Unapplied changes",
  "Appliquer la configuration": "Apply configuration",
  "Appliquer": "Apply",
  "Données de gravure indisponibles": "Engraving data unavailable",
  "Compatibilité non vérifiée": "Compatibility unverified",
  "Structure prise en charge · inventaire et équipement non vérifiés": "Structure supported · inventory and equipment unverified",
  "Exécution non prise en charge": "Execution unsupported",
  "Cible acceptée · exécution bloquée": "Target accepted · execution blocked",

};

export default function loadoutFeature(api, { onApplied = () => {}, execution = () => null, onExecute = null } = {}) {
  api.addTranslations(ENGLISH);
  const data = { list: null, weapons: {}, asking: new Set(), failed: new Set(), saved: null, disposed: false, writes: 0, readAfterWrite: false, farming: null };
  const edits = { mpw18: {}, mpw4: {} };
  const state = { mpw18: { busy: false, error: null, uncertain: false, submitted: null }, mpw4: { busy: false, error: null, uncertain: false, submitted: null } };
  const keyOf = (mode, field) => field === "Stage" ? (mode === "mpw18" ? "stage18" : "stage4") : `${mode}${field}`;
  const loadList = async () => {
    data.list = await withDeadline(api.get('/engravings')).catch(() => null);
    api.refresh();
  };
  const loadSaved = async () => {
    if (Object.values(state).some((part) => part.busy)) { data.readAfterWrite = true; return; }
    const writes = data.writes;
    const answer = await withDeadline(api.get('/loadout')).catch(() => null);
    if (data.disposed || writes !== data.writes) return;
    if (answer?.loadouts) {
      data.saved = answer.loadouts;
      for (const mode of ['mpw18', 'mpw4']) if (state[mode].uncertain) {
        state[mode].uncertain = false;
        state[mode].error = same(answer.loadouts[mode], state[mode].submitted)
          ? null : 'Cible différente sur le serveur · vérifier avant d’appliquer';
      }
    }
    api.refresh();
    return Boolean(answer?.loadouts);
  };
  loadList();
  loadSaved();
  const loadFarming = async () => {
    const answer = await withDeadline(api.get('/farming')).catch(() => null);
    if (data.disposed) return;
    if (answer) data.farming = answer;
    api.refresh();
  };
  loadFarming();
  const farmingTimer = globalThis.window?.setInterval?.(loadFarming, 10000);


  // What a selector shows: the page's option once chosen (null: never
  // chosen; '' chosen empty), else the loadout saved on the server, so
  // that options that never held it show, and keep, what is saved.
  const touched = (mode, field) => api.setting(keyOf(mode, field)) != null;
  const fromServer = (mode, field) => {
    const part = data.saved?.[mode];
    if (field === 'Stage') return part?.stage == null ? '' : String(part.stage);
    if (field === 'Preset') return part?.preset ?? '';
    if (field === 'Weapon') return part?.soul_weapon ? String(part.soul_weapon.id) : '';
    // The saved variant only goes with the saved weapon.
    return part?.soul_weapon && value(mode, 'Weapon') === String(part.soul_weapon.id) ? part.soul_weapon.variant : '';
  };
  const value = (mode, field) => edits[mode][field] ?? (touched(mode, field) ? api.setting(keyOf(mode, field)) : fromServer(mode, field));
  // A choice shows its first entry while untouched: the server's value goes first.
  const firstSaved = (mode, field, choices) => {
    const saved = touched(mode, field) ? '' : fromServer(mode, field);
    const index = saved ? choices.findIndex((choice) => choice.value === saved) : -1;
    return index > 0 ? [choices[index], ...choices.slice(0, index), ...choices.slice(index + 1)] : choices;
  };

  // The chosen weapon's pattern and variants, asked once.
  const weapon = (mode) => {
    const id = Number(value(mode, 'Weapon')) || null;
    if (!id) return null;
    if (!(id in data.weapons) && !data.asking.has(id) && !data.failed.has(id)) {
      data.asking.add(id);
      withDeadline(api.get(`/engraving?id=${id}`)).catch(() => null).then((answer) => {
        if (answer) data.weapons[id] = answer;
        data.asking.delete(id);
        if (!answer) data.failed.add(id);
        api.refresh();
      });
    }
    return data.weapons[id] ?? null;
  };
  const variant = (mode) => {
    const name = value(mode, 'Variant');
    return weapon(mode)?.variants.find((v) => v.name === name) ?? null;
  };

  const presetChoices = (mode) => firstSaved(mode, 'Preset', [
    { value: '', label: api.tr('— choisir —') }, ...PRESETS.map((p) => ({ value: p, label: p })),
  ]);
  const weaponChoices = (mode) => firstSaved(mode, 'Weapon', [
    { value: '', label: api.tr('Sans Soul Weapon demandée') },
    ...(data.list?.weapons ?? []).filter((w) => w.grid).map((w) => ({
      value: String(w.id), label: `${DOTS[w.colour] ?? ''} ${w.stage} · ${w.name}`.trim(),
    })),
  ]);
  const variantChoices = (mode) => firstSaved(mode, 'Variant', [
    { value: '', label: api.tr('— choisir —') },
    ...(weapon(mode)?.variants ?? []).map((v) => ({
      value: v.name, label: v.name,
    })),
  ]);
  // The grid's rows: the pieces' colours, 'empty' for an empty cell,
  // null for a cell that is not part of the grid.
  const gridRows = (mode) => {
    const entry = weapon(mode);
    const chosen = variant(mode);
    if (!entry || !chosen) return [];
    const colour = {};
    chosen.pieces.forEach((piece, index) => {
      for (const [r, c] of piece.cells) colour[`${r},${c}`] = FILLS[piece.colour] ?? TURN[index % TURN.length];
    });
    const active = new Set(entry.cells.map(([r, c]) => `${r},${c}`));
    return Array.from({ length: entry.grid }, (_, row) => Array.from({ length: entry.grid }, (__, col) => {
      const key = `${row},${col}`;
      return colour[key] ?? (active.has(key) ? 'empty' : null);
    }));
  };
  // Only what must be done before placing (Content and Echo, whose
  // grids the wiki's players disagree on): the confidence of the data
  // stays in engravings.json and the README.
  const warned = (mode) => Boolean(variant(mode)) && weapon(mode)?.wiki_check === 'community-differs';
  const applicability = (mode) => variant(mode)?.automation ?? weapon(mode)?.automation;
  const applicabilityText = (mode) => {
    const support = applicability(mode);
    if (!support) return api.tr('Compatibilité non vérifiée');
    return support.supported ? api.tr('Structure prise en charge · inventaire et équipement non vérifiés')
      : api.tr(support.reason_t ?? 'Exécution non prise en charge');
  };
  const acceptedState = (mode) => {
    const support = data.saved?.[mode]?.automation;
    return support && !support.supported && data.saved?.[mode]?.soul_weapon
      ? `${api.tr('Cible acceptée · exécution bloquée')} : ${api.tr(support.reason_t ?? 'Exécution non prise en charge')}`
      : api.tr('Cible acceptée · équipement en jeu à vérifier');
  };

  const currentResult = (mode) => {
    const observed = execution();
    const result = observed?.setup_result;
    const accepted = data.saved?.[mode];
    const age = Date.now() / 1000 - Number(result?.at);
    if (observed?.mode !== mode || result?.mode !== mode
        || !accepted?.revision || result.revision !== accepted.revision
        || !Number.isFinite(age) || age < 0 || age > 120
        || !same(result.target, { stage: accepted.stage ?? null, preset: accepted.preset ?? null,
          soul_weapon: accepted.soul_weapon ?? null })) return null;
    return result;
  };

  const evidence = (mode) => {
    const part = data.saved?.[mode];
    const target = part?.soul_weapon;
    if (!target) return api.tr('Sans Soul Weapon demandée');
    const result = currentResult(mode);
    if (result?.result === 'failed' && result.message_t) return api.tr(result.message_t);
    const observed = execution();
    if (observed?.mode === mode && observed.setup_blocker_t) return api.tr(observed.setup_blocker_t);
    if (result?.result === 'done') return api.tr(part?.automation?.engraving_required === true
      ? 'Soul Weapon et gravure vérifiées · huit cartes verrouillées' : 'Configuration vérifiée');
    const soul = data.farming?.soul_weapon;
    if (!soul) return api.tr('Cible acceptée · équipement en jeu à vérifier');
    const gate = soul.switch === 'off' ? api.tr('Changement automatique de Soul Weapon désactivé')
      : soul.engraving === 'off' ? api.tr('Gravure automatique désactivée · premier passage soumis à supervision') : '';
    const recovery = soul.recovery;
    let proof;
    if (recovery?.required) proof = api.tr('Remise en sécurité nécessaire : les huit cartes ne sont pas confirmées verrouillées');
    else if (recovery && recovery.weapon_id === target.id && recovery.variant === target.variant
        && Number.isFinite(recovery.at) && recovery.at > 0) {
      const time = new Date(recovery.at * 1000).toLocaleString();
      if (recovery.verified && recovery.locks_verified && recovery.phase === 'verified') {
        proof = api.tr('Gravure et verrouillage des huit cartes vérifiés le {time} · contrôle actuel à refaire', { time });
      } else if (recovery.locks_verified) {
        proof = api.tr('Huit cartes revérifiées verrouillées le {time} · gravure demandée non vérifiée', { time });
      } else {
        proof = api.tr('Tentative enregistrée le {time} · arme et gravure à vérifier', { time });
      }
    } else if (recovery?.weapon_id) proof = api.tr('Dernier contrôle : autre arme ou gravure · cible acceptée à vérifier');
    else if (soul.last) proof = api.tr('Dernière tentative : {weapon} · arme et gravure à vérifier',
      { weapon: soul.last.weapon ?? '—' });
    else proof = api.tr('Aucune preuve enregistrée pour cette cible');
    return gate ? `${gate} · ${proof}` : proof;
  };

  const target = (mode) => ({
    stage: Number(value(mode, 'Stage')) || null,
    preset: value(mode, 'Preset') || null,
    soul_weapon: value(mode, 'Weapon') && variant(mode)
      ? { id: Number(value(mode, 'Weapon')), variant: variant(mode).name } : null,
  });
  const invalid = (mode) => {
    if (!data.saved || !data.list) return 'Configuration du serveur indisponible';
    const stage = Number(value(mode, 'Stage'));
    if (!Number.isInteger(stage) || stage < 1 || stage > 99999) return 'Choisir un stage valide';
    if (!PRESETS.includes(value(mode, 'Preset'))) return 'Choisir un préréglage de combat';
    if (data.failed.has(Number(value(mode, 'Weapon')))) return 'Données de gravure indisponibles';
    if (value(mode, 'Weapon') && !variant(mode)) return 'Choisir une gravure valide pour cette arme';
    return null;
  };
  const same = (left, right) => JSON.stringify({ stage: left?.stage ?? null,
    preset: left?.preset ?? null, soul_weapon: left?.soul_weapon ?? null }) === JSON.stringify(right);
  const accepted = (mode) => {
    const part = data.saved?.[mode];
    if (!part) return api.tr('Cible acceptée indisponible');
    const weapon = part.soul_weapon;
    return `Stage ${part.stage ?? '—'} · ${part.preset ?? '—'} · ${weapon
      ? `${part.weapon ?? weapon.id} / ${weapon.variant}` : api.tr('Sans Soul Weapon demandée')}`;
  };
  const save = async (mode) => {
    if (state[mode].busy || invalid(mode)) return;
    const submitted = target(mode);
    const revision = data.saved?.[mode]?.revision;
    data.writes += 1;
    state[mode].submitted = submitted;
    state[mode].busy = true; state[mode].error = null; state[mode].conflict = false; state[mode].uncertain = false; api.refresh();
    try {
      let timedOut = false;
      const result = await withDeadline(api.post('/loadout', { mode, ...submitted,
        ...(revision ? { if_revision: revision } : {}) }), { onLate: loadSaved })
        .catch((error) => { timedOut = error?.code === 'deadline'; return null; });
      if (data.disposed) return;
      const direct = result?.ok ? result.body?.loadouts : null;
      // A lost response does not prove that the write failed. Read back the
      // accepted target before reporting its outcome, without retrying a write.
      const confirmed = direct ?? (await withDeadline(api.get('/loadout')).catch(() => null))?.loadouts;
      if (data.disposed) return;
      if (confirmed?.[mode]) data.saved = confirmed;
      if (result?.status === 409) {
        state[mode].conflict = true;
        state[mode].error = result.body?.error_t ?? 'Configuration modifiée ailleurs : recharge la cible avant d’appliquer';
      } else if (!confirmed?.[mode] || !same(confirmed[mode], submitted)) {
        state[mode].uncertain = timedOut || !confirmed?.[mode];
        state[mode].error = timedOut ? 'Délai dépassé · résultat non confirmé' : result?.body?.error_t ?? result?.body?.error
          ?? (result ? `HTTP ${result.status}` : 'gateway injoignable');
      } else {
        onApplied(mode);
        // Keep later draft edits; this acknowledgement concerns submitted only.
      }
    } catch { state[mode].error = 'gateway injoignable'; }
    finally {
      state[mode].busy = false;
      if (!data.disposed) {
        api.refresh();
        if (data.readAfterWrite) { data.readAfterWrite = false; loadSaved(); }
      }
    }
  };
  const changed = (key, next) => {
    for (const mode of ['mpw18', 'mpw4']) {
      const field = FIELDS.find((name) => key === keyOf(mode, name));
      if (!field) continue;
      edits[mode][field] = next ?? api.setting(key) ?? '';
      if (field === 'Weapon') {
        edits[mode].Variant = '';
        api.adopt?.(`${mode}Variant`, '');
      }
      state[mode].error = null;
      state[mode].conflict = false;
      api.refresh();
    }
  };
  const retry = () => {
    data.failed.clear();
    loadSaved(); loadList();
  };
  const reloadTarget = async (mode) => {
    if (await loadSaved()) {
      state[mode].conflict = false;
      state[mode].error = null;
      api.refresh();
    }
  };
  const setupRequest = (mode) => {
    const request = execution()?.setup_request;
    return onExecute && !execution()?.hold && !state[mode].busy && !state[mode].executing && !invalid(mode)
      && same(data.saved?.[mode], target(mode)) && request?.mode === mode
      && Boolean(data.saved?.[mode]?.revision)
      && request.if_revision === data.saved?.[mode]?.revision ? request : null;
  };
  const execute = async (mode) => {
    const request = setupRequest(mode);
    if (!request) return;
    state[mode].executing = true; api.refresh();
    try { await onExecute(request); }
    finally { state[mode].executing = false; api.refresh(); }
  };

  return {
    // The options of a mode's dialog, in page_mode.js.
    options: (mode, stageChoices = () => []) => [
      { type: 'choice', key: keyOf(mode, 'Stage'), label: mode === 'mpw18' ? 'Stage mpw18' : 'Stage mpw4',
        value: () => String(value(mode, 'Stage')), choices: stageChoices, disabled: () => state[mode].busy },
      {
        type: 'choice', key: `${mode}Preset`, label: 'Préréglage de combat', value: () => value(mode, 'Preset'), disabled: () => state[mode].busy, choices: () => presetChoices(mode),
      },
      { type: 'choice', key: `${mode}Weapon`, label: 'Soul Weapon', value: () => value(mode, 'Weapon'), disabled: () => state[mode].busy, choices: () => weaponChoices(mode) },
      {
        type: 'choice', key: `${mode}Variant`, label: 'Gravure',
        value: () => value(mode, 'Variant'), disabled: () => state[mode].busy, visible: () => Boolean(value(mode, 'Weapon')), choices: () => variantChoices(mode),
      },
      { type: 'grid', label: 'Grille', visible: () => Boolean(variant(mode)), rows: () => gridRows(mode) },
      {
        type: 'status', label: 'Attention', visible: () => warned(mode),
        value: () => api.tr('Grille à vérifier en jeu avant la pose'),
      },
      { type: 'status', label: 'Cible', value: () => `${api.tr('Acceptée')} : ${accepted(mode)}` },
      { type: 'status', label: 'État', value: () => {
        if (state[mode].busy) return api.tr('Enregistrement de la cible…');
        if (state[mode].executing) return api.tr('Application demandée…');
        if (state[mode].error) return `${api.tr('Application non confirmée')} : ${api.tr(state[mode].error)}`;
        const problem = invalid(mode);
        if (problem) return api.tr(problem);
        if (!same(data.saved?.[mode], target(mode))) {
          const support = applicability(mode);
          return `${api.tr('Modifications non appliquées')}${support && !support.supported ? ` · ${applicabilityText(mode)}` : ''}`;
        }
        if (data.saved?.[mode]?.automation?.supported === false && data.saved?.[mode]?.soul_weapon) return acceptedState(mode);
        return evidence(mode);
      }, button: () => !data.saved || !data.list || data.failed.size ? { label: 'Réessayer', run: retry }
        : state[mode].conflict ? { label: 'Recharger la cible', run: () => reloadTarget(mode) }
          : state[mode].uncertain ? { label: 'Vérifier', run: loadSaved }
            : setupRequest(mode) ? { label: 'Réessayer cette configuration', run: () => execute(mode) } : null },
      { type: 'action', label: 'Appliquer la configuration', button: 'Appliquer', run: () => save(mode),
        disabled: () => state[mode].busy || Boolean(invalid(mode)) || same(data.saved?.[mode], target(mode)) },
    ],
    stage: (mode) => data.saved?.[mode]?.stage ?? null,
    onSetting: changed,
    dispose: () => { data.disposed = true; globalThis.window?.clearInterval?.(farmingTimer); },
  };
}
