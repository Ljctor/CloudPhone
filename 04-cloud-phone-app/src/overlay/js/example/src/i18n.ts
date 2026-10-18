// Page languages. The page is written in French; tr() returns the English
// text when English is selected. "{name}" placeholders are filled from
// params. A missing translation falls back to French.

export const LANGUAGES = [
  { id: 'fr', label: 'Français' },
  { id: 'en', label: 'English' },
];

let current = 'fr';

export function defaultLanguage() {
  try {
    return (navigator.language || '').toLowerCase().startsWith('fr') ? 'fr' : 'en';
  } catch {
    return 'fr';
  }
}

export function setLanguage(language) {
  current = language === 'en' ? 'en' : 'fr';
  try {
    document.documentElement.lang = current;
  } catch {
    // No document (tests): nothing to update.
  }
}

export function language() {
  return current;
}

const EN = {
  // Bar and screen
  'Marche arrêt': 'Power',
  'Baisser le volume': 'Volume down',
  'Monter le volume': 'Volume up',
  'Applications récentes': 'Recent apps',
  'Accueil': 'Home',
  'Retour': 'Back',
  'Plein écran': 'Fullscreen',
  'Reconnecter la vidéo': 'Reconnect the video',
  'Connexion {state}': 'Connection {state}',
  'Replier la barre (appui long : barre fixe)': 'Fold the bar (long press: docked bar)',
  'Barre fixe : toucher pour la rendre flottante': 'Docked bar: tap to make it float',
  'Afficher la barre (glisser pour déplacer)': 'Show the bar (drag to move)',
  'Contrôles Android': 'Android controls',
  'Navigation Android': 'Android navigation',
  'Écran Android': 'Android screen',
  'Surface tactile Android': 'Android touch surface',
  'Connexion au flux…': 'Connecting to the stream…',
  'Reconnexion…': 'Reconnecting…',
  'Fermer': 'Close',
  // Panels
  'Serveur': 'Server',
  'Cet appareil': 'This device',
  'État': 'Status',
  'injoignable': 'unreachable',
  'joignable': 'reachable',
  'Service Android': 'Android service',
  'Android démarré': 'Android booted',
  'oui': 'yes',
  'en cours': 'in progress',
  'sans réponse': 'no answer',
  'Appareils connectés': 'Connected devices',
  'Autres appareils': 'Other devices',
  'Déconnecter': 'Disconnect',
  'Un autre appareil a pris la main': 'Another device took over',
  'Touchez ↻ pour la reprendre.': 'Tap ↻ to take it back.',
  'Charge du serveur': 'Server load',
  '{load} tâches pour {cpus} threads': '{load} tasks for {cpus} threads',
  '{load} tâches pour {cpus} threads ({cores} cœurs)': '{load} tasks for {cpus} threads ({cores} cores)',
  '{n} redémarrage': '{n} restart',
  '{n} redémarrages': '{n} restarts',
  'Réseau': 'Network',
  'Ping': 'Ping',
  'Connexion': 'Connection',
  'Chemin': 'Path',
  'Débit vidéo': 'Video bitrate',
  'Paquets perdus': 'Packets lost',
  'Gigue': 'Jitter',
  'Android et flux vidéo': 'Android and video stream',
  'Flux vidéo': 'Video stream',
  'Images envoyées': 'Frames sent',
  'Codec': 'Codec',
  'Affichage': 'Display',
  'Images affichées': 'Frames displayed',
  'Images perdues': 'Frames dropped',
  'Tampon vidéo': 'Video buffer',
  'Écran de l’appareil': 'Device screen',
  'Fenêtre': 'Window',
  'Densité': 'Density',
  'Image affichée': 'Displayed image',
  'Entrées': 'Input',
  'Touches via': 'Touches via',
  'Options': 'Options',
  'Langue': 'Language',
  'Afficher le curseur': 'Show the cursor',
  'Replier la barre 3 s après l’entrée en plein écran': 'Fold the bar 3 s after entering fullscreen',
  'Machine': 'Machine',
  'Processeur': 'Processor',
  '{cpu} % de {cpus} threads': '{cpu} % of {cpus} threads',
  'Fréquence': 'Frequency',
  'Mémoire': 'Memory',
  'Émulateur': 'Emulator',
  '{cores} cœurs · {memory}': '{cores} cores · {memory}',
  'Android': 'Android',
  'Images/s du jeu': 'Game frames/s',
  'Moteur de rendu': 'Renderer',
  'Réglages d’Android': 'Android settings',
  'Événements': 'Events',
  '{app} a planté': '{app} crashed',
  'Alertes sur le téléphone': 'Phone alerts',
  'Non disponibles sur ce serveur.': 'Not available on this server.',
  'Alertes par ntfy (même page fermée)': 'Alerts through ntfy (even with the page closed)',
  'Abonne l’appli ntfy à': 'Subscribe the ntfy app to',
  'Copier l’adresse': 'Copy the address',
  'Copie impossible : touche longuement le lien.': 'Could not copy: long-press the link.',
  'Alerte de test': 'Test alert',
  'Envoyée.': 'Sent.',
  'Échec de l’envoi.': 'Sending failed.',
  'Envoyer': 'Send',
  'Plantages et redémarrages d’Android, et les alertes des plugins. Elles passent par le service public ntfy.sh : quiconque connaît l’adresse peut les lire.':
    'Android crashes and restarts, and the plugins’ alerts. They go through the public ntfy.sh service: anyone who knows the address can read them.',
  '{app} ne répondait plus (ANR)': '{app} stopped responding (ANR)',
  '{app} arrêté par Android': '{app} stopped by Android',
  'Mémoire d’Android insuffisante': 'Android ran low on memory',
  'Android a démarré': 'Android started',
  'Le service Android a démarré': 'The Android service started',
  'La passerelle a démarré': 'The gateway started',
  'mise à jour de {app} (les applis qui en dépendent s’arrêtent)': 'update of {app} (apps that depend on it are stopped)',
  'mémoire insuffisante ({reason})': 'low memory ({reason})',
  '{n} redémarrages automatiques': '{n} automatic restarts',
  'dernier arrêt : {result}': 'last stop: {result}',
  'Journaux d’Android illisibles (adb)': 'Android logs unreadable (adb)',
  'Aucun événement': 'No events',
  'Cœurs': 'Cores',
  'Android va redémarrer avec ces réglages.': 'Android will restart with these settings.',
  'Lavapipe (recommandé)': 'Lavapipe (recommended)',
  'Couleurs justes, le plus rapide sans carte graphique.': 'Right colours, the fastest without a graphics card.',
  'Rapide, mais certaines couleurs du jeu peuvent être fausses.': 'Fast, but some game colours can be wrong.',
  'Couleurs justes, mais lent et très gourmand.': 'Right colours, but slow and very heavy.',
  'Logiciel (défaut de l’émulateur)': 'Software (emulator default)',
  'Rendu logiciel par défaut de l’émulateur.': 'The emulator’s default software renderer.',
  'Cœurs et mémoire': 'Cores and memory',
  'Mémoire Android': 'Android memory',
  'Swap Android': 'Android swap',
  'Flux envoyé': 'Stream sent',
  '{used} utilisés / {total}': '{used} used / {total}',
  'Go': 'GB',
  'Mo': 'MB',
  // Android screen size
  'Appareil': 'Device',
  'Résolution': 'Resolution',
  'Informations : client et serveur': 'Information: client and server',
  'Options et plugins': 'Options and plugins',
  'Informations': 'Information',
  'Client': 'Client',
  'Plugins': 'Plugins',
  'Aucun plugin installé.': 'No plugin installed.',
  '480p (défaut)': '480p (default)',
  'Appliquer': 'Apply',
  'Tablette 16:10': 'Tablet 16:10',
  'Pliable ouvert': 'Foldable, open',
  'Cette fenêtre': 'This window',
  'Indisponible pour le moment.': 'Unavailable for now.',
  'Non disponible sur ce serveur.': 'Not available on this server.',
  'Demande envoyée, en attente du serveur…': 'Request sent, waiting for the server…',
  'Android redémarre en {size}…': 'Android is restarting at {size}…',
  'Échec : {message}': 'Failed: {message}',
  'Passerelle injoignable': 'Gateway unreachable',
  'Erreur {status}': 'Error {status}',
  'Android va redémarrer en {size}.': 'Android will restart at {size}.',
  'Cela prend une à deux minutes. Les applications ouvertes se ferment ; les données sont conservées.':
    'This takes one to two minutes. Open apps close; data is kept.',
  // Status messages
  'Serveur injoignable': 'Server unreachable',
  'Vérifiez que le VPN (WireGuard) est connecté sur cet appareil.':
    'Check that the VPN (WireGuard) is connected on this device.',
  'Changement de résolution': 'Changing resolution',
  'Changement des réglages d’Android': 'Changing Android settings',
  'Android redémarre…': 'Android is restarting…',
  'Android s’est arrêté sur une erreur': 'Android stopped on an error',
  'Il ne redémarre pas tout seul : il faut le relancer sur le serveur.':
    'It will not restart by itself: it must be started again on the server.',
  'Android a planté': 'Android crashed',
  'Redémarrage automatique…': 'Restarting automatically…',
  'Android est arrêté': 'Android is stopped',
  'Il faut le démarrer sur le serveur.': 'It must be started on the server.',
  'Android démarre…': 'Android is starting…',
  'Cela peut prendre une minute.': 'This can take a minute.',
  'Le serveur se reconnecte à Android…': 'The server is reconnecting to Android…',
  'Vidéo interrompue': 'Video interrupted',
  'La vidéo ne se connecte pas': 'The video does not connect',
  'Le réseau bloque peut-être le flux vidéo (UDP). Touchez ↻ pour réessayer.':
    'The network may be blocking the video stream (UDP). Tap ↻ to retry.',
  'Les touches n’arrivent pas à Android': 'Touches do not reach Android',
  'Un autre appareil regarde ce téléphone': 'Another device is watching this phone',
  '{n} autres appareils regardent ce téléphone': '{n} other devices are watching this phone',
  'L’image peut être plus lente.': 'The image may be slower.',
  'Serveur très chargé': 'Server under heavy load',
  'L’image peut ralentir.': 'The image may slow down.',
};

// Plugins bring their own English texts.
export function addTranslations(english) {
  for (const [french, text] of Object.entries(english ?? {})) {
    if (typeof french === 'string' && typeof text === 'string' && !(french in EN)) EN[french] = text;
  }
}

export function tr(text, params) {
  let out = current === 'en' ? (EN[text] ?? text) : text;
  if (params) {
    for (const [key, value] of Object.entries(params)) out = out.split(`{${key}}`).join(String(value));
  }
  return out;
}
