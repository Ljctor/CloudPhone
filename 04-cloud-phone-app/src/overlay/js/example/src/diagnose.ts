// What the page tells the user about the server and the stream: the input
// state in, the status to show out. No React, no DOM. Texts are French
// source text for tr(), with their params when they have some. The page's
// log gets them in English (problemLogEntry).
import { english } from './i18n';

// The single most important thing to tell the user, or null.
// level: 'error' (needs action or will not fix itself), 'wait' (being
// fixed), 'info' (works, but worse than usual). blocking: covers the screen.
export function diagnose({ server, stream, connectingFor, touchFailures }) {
  const value = server.value;
  if (server.failures >= 2) {
    return {
      level: 'error', blocking: true, text: 'Serveur injoignable',
      detail: 'Vérifiez que le VPN (WireGuard) est connecté sur cet appareil.',
    };
  }
  if (value?.kicked) {
    return {
      level: 'error', blocking: true, text: 'Un autre appareil a pris la main',
      detail: 'Touchez ↻ pour la reprendre.',
    };
  }
  const display = value?.display?.state;
  if (display === 'pending' || display === 'applying') {
    return { level: 'wait', blocking: true, text: 'Changement de résolution', detail: 'Android redémarre…' };
  }
  const settingsChange = value?.settings?.state;
  if (settingsChange === 'pending' || settingsChange === 'applying') {
    return { level: 'wait', blocking: true, text: 'Changement des réglages d’Android', detail: 'Android redémarre…' };
  }
  const unit = value?.emulator;
  if (unit) {
    if (unit.active === 'failed') {
      return {
        level: 'error', blocking: true, text: 'Android s’est arrêté sur une erreur',
        detail: 'Il ne redémarre pas tout seul : il faut le relancer sur le serveur.',
      };
    }
    if (unit.active === 'activating' && unit.sub === 'auto-restart') {
      return { level: 'wait', blocking: true, text: 'Android a planté', detail: 'Redémarrage automatique…' };
    }
    if (unit.active === 'inactive' || unit.active === 'deactivating') {
      return { level: 'error', blocking: true, text: 'Android est arrêté', detail: 'Il faut le démarrer sur le serveur.' };
    }
    if (unit.active === 'activating') {
      return { level: 'wait', blocking: true, text: 'Android démarre…', detail: null };
    }
  }
  const booted = value?.android?.booted;
  if (value && booted === false) {
    return { level: 'wait', blocking: stream !== 'connected', text: 'Android démarre…', detail: 'Cela peut prendre une minute.' };
  }
  if (value && booted === null) {
    return { level: 'wait', blocking: stream !== 'connected', text: 'Le serveur se reconnecte à Android…', detail: null };
  }
  if (stream === 'blocked') {
    return {
      level: 'info', blocking: true, text: 'Touchez l’écran pour lancer la vidéo',
      detail: 'Le navigateur bloque la lecture automatique.',
    };
  }
  if (stream === 'disconnected') {
    return { level: 'wait', blocking: true, text: 'Vidéo interrompue', detail: 'Reconnexion…' };
  }
  if (stream !== 'connected' && connectingFor >= 15) {
    return {
      level: 'error', blocking: true, text: 'La vidéo ne se connecte pas',
      detail: 'Le réseau bloque peut-être le flux vidéo (UDP). Touchez ↻ pour réessayer.',
    };
  }
  if (touchFailures >= 3) {
    return { level: 'error', blocking: false, text: 'Les touches n’arrivent pas à Android', detail: null };
  }
  if (stream === 'connected' && value?.viewers > 1) {
    const others = value.viewers - 1;
    return {
      level: 'info', blocking: false,
      text: others === 1 ? 'Un autre appareil regarde ce téléphone' : '{n} autres appareils regardent ce téléphone',
      params: { n: others },
      detail: 'L’image peut être plus lente.',
    };
  }
  if (value?.load && value.load.one > value.load.cpus) {
    return { level: 'info', blocking: false, text: 'Serveur très chargé', detail: 'L’image peut ralentir.' };
  }
  return null;
}

// The page log's line for a new status: [level, text], errors with what to
// do when the status does not say.
export function problemLogEntry(problem) {
  const level = { error: 'error', wait: 'warning', info: 'normal' }[problem.level];
  const detail = problem.detail ? english(problem.detail) : level === 'error' ? english('Touchez ↻ pour réessayer.') : '';
  const text = english(problem.text, problem.params);
  return [level, detail ? `${text}: ${detail}` : text];
}

// Which status this is, params included: a closed banner stays closed for it.
export function problemKey(problem) {
  return problem ? english(problem.text, problem.params) : null;
}

// Whether the status shows as a closable banner: it does not cover the
// screen and the user has not closed this text.
export function bannerShown(problem, dismissed) {
  return Boolean(problem && !problem.blocking && dismissed !== problemKey(problem));
}
