// Log records and toasts as plain data: which records a list keeps and
// shows, and how a new notify record changes the open toasts. No React, no
// DOM (see logs.tsx).
//
// Records are {time, level, source, text, notify?}: level 'normal',
// 'warning' or 'error'; source 'page' for this page's own (Client tab),
// 'gateway', 'emulator' or 'adb' for the server's (GET /api/v1/logs, Server
// tab). Their text is English, shown as it is in either language.

export const LOG_KEPT = 200;
// Colours, at display time only: the theme's foreground, orange, red.
export const LOG_COLORS = { normal: '#fff', warning: '#ff9f0a', error: '#ff453a' };

export const LOG_FILTERS = [
  { id: 'all', label: 'Tout', levels: ['normal', 'warning', 'error'] },
  { id: 'warnings', label: 'Avertissements et erreurs', levels: ['warning', 'error'] },
  { id: 'errors', label: 'Erreurs', levels: ['error'] },
];

// Newest first, the last LOG_KEPT kept.
export function keepRecord(list, record) {
  list.unshift(record);
  list.length = Math.min(list.length, LOG_KEPT);
}

// The records a list shows for a filter id, newest first by time: the
// server's first read of Android's logs adds older events after newer
// records.
export function shownRecords(entries, filter) {
  const levels = (LOG_FILTERS.find((item) => item.id === filter) ?? LOG_FILTERS[0]).levels;
  return entries.filter((entry) => levels.includes(entry.level)).sort((a, b) => b.time - a.time);
}

// Toasts: the same text again adds to the open toast instead of a new one;
// normal ones go after a few seconds, warnings a bit later, errors stay
// until closed.
export const TOAST_MS = { normal: 6000, warning: 12000 };
export const TOASTS_SHOWN = 4;

export function toastKey(record, text) {
  return `${record.level}|${record.source}|${text}`;
}

// The open toasts once this record's toast is shown.
export function withToast(list, record, text) {
  const key = toastKey(record, text);
  const same = list.find((toast) => toast.key === key);
  const next = same
    ? list.map((toast) => (toast.key === key ? { ...toast, count: toast.count + 1 } : toast))
    : [...list, { key, level: record.level, source: record.source, text, count: 1 }];
  return next.slice(-TOASTS_SHOWN);
}
