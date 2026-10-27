// Slayer Legend plugin, page side: loaded by the Cloud Phone page (see
// plugins.ts in part 04 for the API). This file only assembles the
// features, one module per feature beside it, each a function of the page
// API returning its options, its onSetting and dispose hooks and, for the
// mode, its overlay hook (its lines top left), and, for the developer, its
// debug rows (the plugin's last section, « Debug & développement »).
// Labels are French with their English in ENGLISH below; the gateway's
// texts are {template, params}, their English in templates.json (GET
// /templates). Log records are English, shown as they come.
// The parts:
// - page_screen.js: the game's screen (debug) and stage (its row under
//   the mode's État).
// - page_power.js: the plugin's on/off switch, at the top: while off the
//   gateway taps nothing and nothing is drawn over the game. (The game is
//   launched by the watchdog's relaunch only: no button.)
// - page_mode.js: the mode and its timer ("Mode et farming").
// - page_gold.js: gold per second ("Gold"), written in the game's top bar,
//   and the mode's lines top left, in the gold counter's font
//   (gold_text.js); it calls the overlay hooks while the overlay applies.
// - page_trace.js: "Enregistrer mes parcours" (on by default): each tap
//   the user makes on the game is sent to the gateway, which records the
//   screen before and after it (never replayed). In the debug section.
// - page_watchdog.js: the gateway's watchdog at its last look on the
//   selected mode and « Réessayer », at the end of the mode's État row;
//   the lease and its counters in the debug section.
// - page_game.js: the game's state the gateway scanned, one section per
//   screen (GET /game), greyed while not read again since a relaunch.
// - page_counters.js: the emerald and diamond counters, on this screen
//   only (nothing is sent to Android), cut at their comma or rewritten
//   (counter_rewrite.js, with emerald_mask.js and emerald_font.js).
import counters from './page_counters.js';
import game from './page_game.js';
import gold from './page_gold.js';
import power from './page_power.js';
import { SWORD } from './page_icons.js';
import mode from './page_mode.js';
import navigationDebug from './page_navigation_debug.js';
import screen from './page_screen.js';
import trace from './page_trace.js';
import watchdog from './page_watchdog.js';

const ENGLISH = {
  'Étage à farmer': 'Floor to farm',
  'défaut': 'default',
  'Gold': 'Gold',
  'Gold par heure': 'Gold per hour',
  'Âmes par heure': 'Souls per hour',
  'Autres débits/h': 'Other rates/h',
  'Zones de navigation': 'Navigation zones',
  'Légende navigation': 'Navigation legend',
  'Écran non identifié': 'Unidentified screen',
  'Écran : {screen}': 'Screen: {screen}',
  'Enregistrer un clic': 'Record a tap',
  'Capture avant…': 'Capturing before…',
  'Clique dans le jeu': 'Tap in the game',
  'Capture après…': 'Capturing after…',
  'Réessayer le clic': 'Retry recording',
  'condition à vérifier': 'condition to check',
  'Jaune : clic · bleu : vertical · violet : horizontal · pointillés : condition à vérifier':
    'Yellow: tap · blue: vertical · purple: horizontal · dashed: condition to check',
  '{mode} · en attente : tu joues · nouvel essai dans {seconds} s': '{mode} · on hold: you are playing · next try in {seconds} s',
  'Reprendre': 'Resume',
  'Affiché': 'Shown',
  'Masqué': 'Hidden',
  'pas encore mesuré': 'not measured yet',
  'non visible': 'not visible',
  'Mode par défaut': 'Default mode',
  'Farming mpw4': 'mpw4 farming',
  'Farming mpw18': 'mpw18 farming',
  'Jeu libre': 'Free play',
  'Agent mode': 'Agent mode',
  'Affichage': 'Display',
  'Analyse': 'Analysis',
  'Capture': 'Capture',
  'Capture enregistrée': 'Saved capture',
  'Relevé historique': 'Historical reading',
  'Débits': 'Rates',
  'Mine fermée': 'Closed Mine',
  'Stage mpw18': 'mpw18 stage',
  'Stage mpw4': 'mpw4 stage',
  '— choisir —': '— choose —',
  'État': 'State',
  'Zone à farmer': 'Area to farm',
  'Temps restant': 'Time left',
  'Ajuster (minutes)': 'Adjust (minutes)',
  'plus de parchemin doré': 'no gold scroll',
  'Sans limite': 'No limit',
  'reste {time}': '{time} left',
  'Mine': 'Mine',
  'Choisis l’étage et la zone': 'Choose the floor and the area',
  'Plugin': 'Plugin',
  'Compteur d’émeraudes': 'Emerald counter',
  'Mode et farming': 'Mode and farming',
  'Émeraudes': 'Emeralds',
  'Diamants': 'Diamonds',
  'Compteur de diamants': 'Diamond counter',
  'Inchangé': 'Unchanged',
  'Coupé à la virgule': 'Cut at the comma',
  'Réécrit': 'Rewritten',
  'Nombre affiché (vide : après la virgule)': 'Number shown (empty: after the comma)',
  'détecté': 'detected',
  'non détecté': 'not detected',
  'Écran détecté': 'Detected screen',
  'Écran titre': 'Title screen',
  'Choix de la sauvegarde': 'Save choice',
  'Aucun panneau ouvert': 'No panel open',
  'Économie d’énergie': 'Power Saving',
  'Autre (menu, chargement…)': 'Other (menu, loading…)',
  'Pas de capture d’écran': 'No screenshot',
  'Menu du jeu': 'Game menu',
  'Autre application': 'Another app',
  'inconnu': 'unknown',
  'Arme': 'Weapon',
  'Accessoire': 'Accessory',
  'Stage': 'Stage',
  '{n} par vague': '{n} per wave',
  'Enregistrer mes parcours': 'Record my paths',
  'Activé': 'On',
  'Désactivé': 'Off',
  'Parcours enregistrés': 'Recorded paths',
  '{nodes} écrans, {taps} appuis': '{nodes} screens, {taps} taps',
  'indisponible (gateway sans dossier de données)': 'unavailable (the gateway has no data directory)',
  'Bail': 'Lease',
  'En pause : entrée dans le mode {mode}': 'Paused: entering {mode}',
  '{holder} ({reason})': '{holder} ({reason})',
  'libre': 'free',
  'Surveillance': 'Watchdog',
  '{looks} vérifications, {bad} échecs d’affilée, {alerts} alertes': '{looks} looks, {bad} bad in a row, {alerts} alerts',
  'Debug & développement': 'Debug & development',
  'Détection des émeraudes': 'Emerald detection',
  'Détection des diamants': 'Diamond detection',
  'Réessayer': 'Retry',
  'État du jeu': 'Game state',
  'Case équipée': 'Equipped slot',
  'Défi': 'Challenge',
  'Niveau affiché sur les armes': 'Level shown on weapons',
  'Promotion affichée': 'Shown promotion',
  'Promotion sélectionnée': 'Selected promotion',
  'Promotions observées': 'Observed promotions',
  'Relevé historique · x/5 : progression affichée, possession non confirmée': 'Historical reading · x/5: displayed progress, ownership unconfirmed',
  'Terminé': 'Complete',
  'x/5 : progression affichée par le jeu ; possession non confirmée': 'x/5: progress displayed by the game; ownership unconfirmed',
  'Équipé': 'Equipped',
  'Gris': 'Grey',
  'Vert': 'Green',
  'Violet': 'Purple',
  'Rouge': 'Red',
  'Bleu': 'Blue',
  'Or': 'Gold',
  'vu à {time}': 'seen at {time}',
};

export default function activate(api) {
  api.addTranslations(ENGLISH);
  // The gateway's texts come as {template, params} (a field's `_t`, the
  // watchdog's line and status): their English is templates.json's, served
  // by the gateway. Without it they show in French.
  api.get('/templates').catch(() => null).then((templates) => {
    if (!templates || typeof templates !== 'object') return;
    api.addTranslations(templates);
    api.refresh();
  });
  // Started in this order (each asks the gateway as it starts)...
  // Turning the plugin on or off redraws what the parts draw (below).
  const powerPart = power(api, { changed: () => drawers.forEach((part) => part.update()) });
  const counterPart = counters(api, { enabled: powerPart.on });
  const screenPart = screen(api);
  const watchdogPart = watchdog(api);
  const modePart = mode(api, { known: screenPart.known, watchdog: watchdogPart, stage: screenPart.stage });
  const goldPart = gold(api, { overlay: [modePart.overlay], enabled: powerPart.on });
  const drawers = [counterPart, goldPart];
  const tracePart = trace(api);
  const navigationDebugPart = navigationDebug(api, { enabled: powerPart.on });
  drawers.push(navigationDebugPart);
  const gamePart = game(api, { resourceOptions: goldPart.resourceOptions,
    displayOptions: [...counterPart.options, ...goldPart.displayOptions] });
  const parts = [powerPart, counterPart, screenPart, modePart, goldPart, tracePart,
    navigationDebugPart, watchdogPart, gamePart];
  // ...and shown in this one, then « Debug & développement », last and
  // folded: the parts' developer rows and the plugin's log records.
  const shown = [powerPart, modePart];
  const debug = [
    { type: 'section', key: 'debug', label: 'Debug & développement', folded: true },
    ...[screenPart, counterPart, watchdogPart, tracePart, navigationDebugPart].flatMap((part) => part.debug ?? []),
    { type: 'log', match: (record) => record.source === api.id },
  ];
  const options = [...shown.flatMap((part) => part.options), ...debug];
  // The game's sections before « Debug & développement ».
  gamePart.rows(options, options.length - debug.length);
  return {
    icon: SWORD,
    options,
    onSetting: (key, value) => {
      for (const part of parts) part.onSetting?.(key, value);
    },
    dispose: () => {
      for (const part of parts) part.dispose?.();
    },
  };
}
