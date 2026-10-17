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
  'Serveur, réseau et Android': 'Server, network and Android',
  'Cet appareil, affichage et options': 'This device, display and options',
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
  '{load} / {cpus} cœurs': '{load} / {cpus} cores',
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
  'Point sous le doigt': 'Dot under the finger',
  'Compteur d’émeraudes': 'Emerald counter',
  'détecté': 'detected',
  'non détecté': 'not detected',
  'Masquer les décimales des émeraudes (Slayer Legend)': 'Hide the emerald decimals (Slayer Legend)',
  'Replier la barre 3 s après l’entrée en plein écran': 'Fold the bar 3 s after entering fullscreen',
  'Configuration serveur': 'Server settings',
  'Configuration client': 'Client settings',
  'Écran d’Android': 'Android screen',
  // Android screen size
  'Appareil': 'Device',
  'Résolution': 'Resolution',
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

export function tr(text, params) {
  let out = current === 'en' ? (EN[text] ?? text) : text;
  if (params) {
    for (const [key, value] of Object.entries(params)) out = out.split(`{${key}}`).join(String(value));
  }
  return out;
}
