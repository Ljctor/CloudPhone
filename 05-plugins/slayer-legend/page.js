// Slayer Legend plugin, page side: loaded by the Cloud Phone page (see
// plugins.ts in part 04 for the API). This file only assembles the
// features, one module per feature beside it, each a function of the page
// API returning its options, its onSetting and dispose hooks and, for the
// mode, its overlay hook (its lines top left):
// - page_screen.js: the game's screen and stage ("Jeu").
// - page_launch.js: "Lancer le jeu": the gateway starts the game and
//   brings it to the battle screen (TAP TO START, then Confirm).
// - page_mode.js: the mode and its timer ("Mode et farming").
// - page_gold.js: gold per second ("Gold"), written in the game's top bar,
//   and the mode's lines top left, in the gold counter's font
//   (gold_text.js); it calls the overlay hooks while the overlay applies.
// - page_trace.js: "Enregistrer mes parcours" (on by default): each tap
//   the user makes on the game is sent to the gateway, which records the
//   screen before and after it (never replayed).
// - page_watchdog.js: "Surveillance mpw18", the gateway's mpw18 watchdog
//   at its last look, and the shared lease's outside holder.
// - page_counters.js: the emerald and diamond counters, on this screen
//   only (nothing is sent to Android), cut at their comma or rewritten
//   (counter_rewrite.js, with emerald_mask.js and emerald_font.js).
import counters from './page_counters.js';
import gold from './page_gold.js';
import launch from './page_launch.js';
import mode from './page_mode.js';
import screen from './page_screen.js';
import trace from './page_trace.js';
import watchdog from './page_watchdog.js';

const ENGLISH = {
  'Farmer la mine': 'Farm the mine',
  'Étage à farmer': 'Floor to farm',
  'Mode': 'Mode',
  'défaut': 'default',
  'Configuration : farming mpw18': 'Settings: mpw18 farming',
  'Configuration : farming mpw4': 'Settings: mpw4 farming',
  'Configuration : mine fermée': 'Settings: Closed Mine',
  'Arme, gravure, réglages de combat': 'Weapon, engraving, battle settings',
  'à venir': 'coming',
  'Plumes': 'Feathers',
  'Gold': 'Gold',
  'Gold par seconde': 'Gold per second',
  'Overlay gold/s': 'Gold/s overlay',
  'Affiché': 'Shown',
  'Masqué': 'Hidden',
  'pas encore mesuré': 'not measured yet',
  'non visible (économie d’énergie ?)': 'not visible (Power Saving Mode?)',
  'Farming mpw18 (par défaut)': 'mpw18 farming (default)',
  'Farming mpw4': 'mpw4 farming',
  'Farming mpw18': 'mpw18 farming',
  'Jeu libre': 'Free play',
  'Mine fermée': 'Closed Mine',
  'Configuration : jeu libre': 'Settings: free play',
  'Stage mpw18': 'mpw18 stage',
  'Stage mpw4': 'mpw4 stage',
  '— choisir —': '— choose —',
  'État': 'State',
  'Zone à farmer': 'Area to farm',
  'Minuteur': 'Timer',
  'Ajuster (minutes)': 'Adjust (minutes)',
  'plus de parchemin doré': 'no gold scroll',
  'Combat en cours, sans parchemin doré': 'Fighting, without the gold scroll',
  'Sans limite': 'No limit',
  'reste {time}': '{time} left',
  'Durée écoulée : « Repeat entry » décoché, la mine s’arrête après cette entrée':
    'Time is up: "Repeat entry" unticked, the mine stops after this entry',
  'Durée écoulée : pas de relance': 'Time is up: no restart',
  'Durée écoulée, mais « Repeat entry » ne se décoche pas': 'Time is up, but "Repeat entry" does not untick',
  'Mine': 'Mine',
  'Surveillance de la mine': 'Watching the mine',
  'Combat en cours, parchemin doré actif': 'Fighting, gold scroll on',
  'Mine relancée': 'Mine started again',
  'Le jeu n’est pas au premier plan': 'The game is not in front',
  'Écran autre que la mine : rien à faire': 'Not a mine screen: nothing to do',
  'Parchemin doré pas vu depuis 5 minutes : pas de relance': 'Gold scroll not seen for 5 minutes: no restart',
  'Plus de parchemin doré : « Repeat entry » décoché, la mine s’arrête après cette entrée':
    'Gold scroll gone: "Repeat entry" unticked, the mine stops after this entry',
  'Plus de parchemin doré, mais « Repeat entry » ne se décoche pas': 'Gold scroll gone, but "Repeat entry" does not untick',
  'La relance a échoué 3 fois : relance la mine à la main': 'Restarting failed 3 times: start the mine by hand',
  'Choisis l’étage et la zone': 'Choose the floor and the area',
  'Farming mpw4 : choisis d’abord son stage': 'mpw4 farming: choose its stage first',
  'Mine fermée : choisis d’abord l’étage (1 à 9999) et la zone (1 à 5)':
    'Closed Mine: choose the floor (1 to 9999) and the area (1 to 5) first',
  'arrêtée': 'off',
  'Lancer le jeu': 'Launch the game',
  'Lancer': 'Launch',
  'Lancement': 'Launch',
  'Compteur d’émeraudes': 'Emerald counter',
  'Jeu': 'Game',
  'Mode et farming': 'Mode and farming',
  'Émeraudes': 'Emeralds',
  'Diamants': 'Diamonds',
  'Compteur de diamants': 'Diamond counter',
  'Inchangé': 'Unchanged',
  'Coupé à la virgule': 'Cut at the comma',
  'Réécrit': 'Rewritten',
  'Détection du compteur': 'Counter detection',
  'Nombre affiché (vide : après la virgule)': 'Number shown (empty: after the comma)',
  'détecté': 'detected',
  'non détecté': 'not detected',
  'Ouverture du jeu': 'Opening the game',
  'Écran titre touché, connexion': 'Title screen tapped, signing in',
  'Dernière sauvegarde confirmée, chargement': 'Latest save confirmed, loading',
  'Le jeu est sur l’écran de combat': 'The game is on the battle screen',
  'Sortie du mode économie d’énergie': 'Leaving Power Saving Mode',
  'Le mode économie d’énergie ne se ferme pas : touche son bouton à la main': 'Power Saving Mode does not close: tap its button by hand',
  'Écran inattendu : termine le lancement à la main': 'Unexpected screen: finish the launch by hand',
  'Le jeu n’a pas atteint l’écran de combat en 3 minutes': 'The game did not reach the battle screen in 3 minutes',
  'Android ne répond pas': 'Android does not answer',
  'Un lancement est déjà en cours': 'A launch is already running',
  'Écran détecté': 'Detected screen',
  'Écran titre': 'Title screen',
  'Choix de la sauvegarde': 'Save choice',
  'Combat': 'Battle',
  'Économie d’énergie': 'Power Saving',
  'Autre (menu, chargement…)': 'Other (menu, loading…)',
  'Pas de capture d’écran': 'No screenshot',
  'Menu du jeu': 'Game menu',
  'Autre application': 'Another app',
  'Stage sélectionné': 'Selected stage',
  'vu en mode économie d’énergie, à confirmer': 'seen in Power Saving Mode, to be confirmed',
  'inconnu : passe en mode économie d’énergie pour le lire': 'unknown: go to Power Saving Mode to read it',
  'Monstres par vague': 'Monsters per wave',
  'Équipement lâché': 'Equipment dropped',
  'Arme': 'Weapon',
  'Accessoire': 'Accessory',
  'Commun': 'Common',
  'Supérieur': 'Great',
  'Épique': 'Epic',
  'Légendaire': 'Legendary',
  'Couleur des âmes': 'Soul colour',
  'verte': 'green',
  'bleue': 'blue',
  'rouge': 'red',
  'déduite, non vérifiée': 'deduced, not checked',
  'Navigation': 'Navigation',
  'Enregistrer mes parcours': 'Record my paths',
  'Activé': 'On',
  'Désactivé': 'Off',
  'Parcours enregistrés': 'Recorded paths',
  '{nodes} écrans, {taps} appuis': '{nodes} screens, {taps} taps',
  'indisponible (gateway sans dossier de données)': 'unavailable (the gateway has no data directory)',
  'Surveillance mpw18': 'mpw18 watch',
  'Bail': 'Lease',
  '{holder} : {reason}': '{holder}: {reason}',
  'Démarrage': 'Starting',
  'OK (numéral {numeral})': 'OK (numeral {numeral})',
  'OK (économie d’énergie)': 'OK (Power Saving)',
  'En pause : mode {mode}': 'Paused: mode {mode}',
  'En pause : l’utilisateur joue': 'Paused: the user is playing',
  'Lancement du jeu en cours': 'Launching the game',
  'Réparation en cours : {repair}': 'Repair under way: {repair}',
  'Erreur : {error}': 'Error: {error}',
  'pas de vérification (pas de capture d’écran)': 'not checked (no screenshot)',
  'menu du jeu ouvert': 'game menu open',
  'adb ne répond pas : l’émulateur ou adb manque': 'adb does not answer: the emulator or adb is missing',
  'le jeu ne tourne pas': 'the game is not running',
  'une autre application est au premier plan': 'another app is in front',
  'le jeu a planté (fenêtre d’erreur d’Android)': 'the game crashed (Android’s error window)',
  'le jeu est revenu à son écran titre': 'the game is back on its title screen',
  'écran inconnu après la fin du mode (connecté sur un autre appareil ? choix de sauvegarde ?) : à faire à la main':
    'unknown screen after the mode ended (signed in on another device? a choice of saves?): do it by hand',
  'un menu du jeu est ouvert depuis plus d’une minute sans l’utilisateur': 'a game menu has been open over a minute without the user',
  'mauvais stage : pas le stage {stage}': 'wrong stage: not stage {stage}',
  'mauvais préréglage de combat : pas le {preset}': 'wrong battle settings preset: not {preset}',
  'mauvais équipement : {what}': 'wrong equipment: {what}',
  'écran inattendu': 'unexpected screen',
  'le jeu ne répond pas (fenêtre d’Android), « Attendre » sans effet : à faire à la main':
    'the game is not responding (Android’s window), « Wait » did not help: do it by hand',
  // The watchdog's log records.
  'Farming mpw18 : adb ne répond pas : l’émulateur ou adb manque': 'mpw18 farming: adb does not answer: the emulator or adb is missing',
  'Farming mpw18 : le jeu ne tourne pas': 'mpw18 farming: the game is not running',
  'Farming mpw18 : une autre application est au premier plan': 'mpw18 farming: another app is in front',
  'Farming mpw18 : le jeu a planté (fenêtre d’erreur d’Android)': 'mpw18 farming: the game crashed (Android’s error window)',
  'Farming mpw18 : le jeu ne répond pas (fenêtre d’Android), « Attendre » sans effet : à faire à la main':
    'mpw18 farming: the game is not responding (Android’s window), « Wait » did not help: do it by hand',
  'Farming mpw18 : le jeu est revenu à son écran titre': 'mpw18 farming: the game is back on its title screen',
  'Farming mpw18 : écran inconnu après la fin du mode (connecté sur un autre appareil ? choix de sauvegarde ?) : à faire à la main':
    'mpw18 farming: unknown screen after the mode ended (signed in on another device? a choice of saves?): do it by hand',
  'Farming mpw18 : un menu du jeu est ouvert depuis plus d’une minute sans l’utilisateur':
    'mpw18 farming: a game menu has been open over a minute without the user',
  'Farming mpw18 : mauvais stage : pas le stage {stage}': 'mpw18 farming: wrong stage: not stage {stage}',
  'Farming mpw18 : mauvais préréglage de combat : pas le {preset}': 'mpw18 farming: wrong battle settings preset: not {preset}',
  'Farming mpw18 : mauvais équipement : {what}': 'mpw18 farming: wrong equipment: {what}',
  'Farming mpw18 : écran inattendu': 'mpw18 farming: unexpected screen',
  'Farming mpw18 : rétabli': 'mpw18 farming: back',
  'Réparation : {repair}': 'Repair: {repair}',
  'Réparation réussie : {repair}': 'Repair done: {repair}',
  'Réparation sans effet : {repair}, surveillance seule 2 minutes': 'Repair without effect: {repair}, watching only for 2 minutes',
  'Réparation bloquée : {repair}, {cap} fois en une heure ; fais-le à la main': 'Repair blocked: {repair}, {cap} times in an hour; do it by hand',
  'Réparation différée : bail tenu par {holder}': 'Repair deferred: lease held by {holder}',
  'Le jeu ne répond pas : « Attendre » touché': 'The game is not responding: « Wait » pressed',
  'Le jeu ne répond pas : bouton « Attendre » introuvable': 'The game is not responding: « Wait » not found',
  'relance du jeu': 'game relaunch',
  'retour au combat': 'back to battle',
  'Fenêtre « l’application s’arrête » fermée, réouverture du jeu': 'The "app keeps stopping" window was closed, opening the game again',
  'Fenêtre « l’application s’arrête » : bouton introuvable, ferme-la à la main': 'The "app keeps stopping" window: its button was not found, close it by hand',
  'Le jeu plante encore : relance-le à la main': 'The game keeps crashing: relaunch it by hand',
};

export default function activate(api) {
  api.addTranslations(ENGLISH);
  // Started in this order (each asks the gateway as it starts)...
  const counterPart = counters(api);
  const launchPart = launch(api);
  const screenPart = screen(api);
  const modePart = mode(api, { known: screenPart.known });
  const goldPart = gold(api, { overlay: [modePart.overlay] });
  const tracePart = trace(api);
  const watchdogPart = watchdog(api);
  const parts = [counterPart, launchPart, screenPart, modePart, goldPart, tracePart, watchdogPart];
  // ...and shown in this one.
  const shown = [screenPart, launchPart, modePart, watchdogPart, goldPart, tracePart, counterPart];
  return {
    options: shown.flatMap((part) => part.options),
    onSetting: (key, value) => {
      for (const part of parts) part.onSetting?.(key, value);
    },
    dispose: () => {
      for (const part of parts) part.dispose?.();
    },
  };
}
