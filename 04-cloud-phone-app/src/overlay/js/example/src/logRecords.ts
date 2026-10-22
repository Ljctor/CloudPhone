// Log records as plain data: which records a list keeps and shows. No
// React, no DOM (see logs.tsx).
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
