// One log, two outputs: the page's own records (Client tab) and the
// server's (GET /api/v1/logs, Server tab), both newest first. Nothing pops
// up over the screen: alerts reach the user's phone through ntfy only
// (gateway side), and their records are read here in the lists. The page's
// warnings and errors also go to the browser's console at their level. See
// logRecords.ts for the records.
import { useEffect, useState } from 'react';
import { onStreamDiagnostic } from '../../src/components/emulator/net/stream_diagnostics';
import { language, tr } from './i18n';
import { styles } from './styles';
import {
  LOG_COLORS, LOG_FILTERS, keepRecord, shownRecords,
} from './logRecords';

const PAGE_LOG = [];
const SERVER_LOG = [];
const logListeners = new Set();
const CONSOLE = { warning: console.warn.bind(console), error: console.error.bind(console) };

function logChanged() {
  logListeners.forEach((listener) => listener());
}

export function pageLog(level, text, { toConsole = true } = {}) {
  const record = { time: Date.now() / 1000, level, source: 'page', text };
  keepRecord(PAGE_LOG, record);
  if (toConsole) CONSOLE[level]?.(text);
  logChanged();
}

// Structured WebRTC milestones remain visible in the Client tab's existing log.
onStreamDiagnostic((record) => pageLog('normal',
  `WebRTC #${record.session} ${record.event} ${JSON.stringify(record.data)}`, { toConsole: false }));

for (const [method, level] of [['warn', 'warning'], ['error', 'error']]) {
  const original = console[method].bind(console);
  console[method] = (...args) => {
    original(...args);
    pageLog(level, args.map((arg) => (arg instanceof Error ? arg.message
      : typeof arg === 'string' ? arg : (() => { try { return JSON.stringify(arg); } catch { return String(arg); } })())).join(' '),
    { toConsole: false });
  };
}
window.addEventListener('error', (event) => pageLog('error', event.message, { toConsole: false }));
window.addEventListener('unhandledrejection',
  (event) => pageLog('error', String(event.reason?.message ?? event.reason), { toConsole: false }));

// Reads the server's new records every few seconds, whatever is open. A
// restarted gateway answers an old cursor with all its records.
const SERVER_LOG_MS = 4000;
export function useServerLog(gatewayUrl) {
  useEffect(() => {
    let cancelled = false;
    let cursor = '';
    const load = () => fetch(`${gatewayUrl}/api/v1/logs?since=${encodeURIComponent(cursor)}`, { cache: 'no-store' })
      .then((response) => (response.ok ? response.json() : null))
      .then((value) => {
        if (cancelled || !value) return;
        cursor = value.cursor ?? '';
        const records = value.records ?? [];
        records.forEach((record) => keepRecord(SERVER_LOG, record));
        if (records.length) logChanged();
      })
      .catch(() => {});
    load();
    const timer = window.setInterval(load, SERVER_LOG_MS);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [gatewayUrl]);
}

// The server's records kept so far, newest first (as the lists show them).
export function serverRecords() {
  return SERVER_LOG;
}

export function useLog(enabled) {
  const [, setCount] = useState(0);
  useEffect(() => {
    if (!enabled) return undefined;
    const listener = () => setCount((count) => count + 1);
    logListeners.add(listener);
    return () => { logListeners.delete(listener); };
  }, [enabled]);
  return { page: PAGE_LOG, server: SERVER_LOG };
}

export function LogList({ entries, filter, rowStyle, labelStyle }) {
  const locale = language() === 'en' ? 'en-GB' : 'fr-FR';
  const shown = shownRecords(entries, filter);
  if (shown.length === 0) return <div style={rowStyle}>{tr('Rien pour l’instant')}</div>;
  return shown.slice(0, 100).map((entry, index) => (
    <div key={`${entry.time}-${index}`} style={{ ...rowStyle, alignItems: 'flex-start' }} data-level={entry.level}>
      <span style={{ ...labelStyle, whiteSpace: 'nowrap' }}>
        {new Date(entry.time * 1000).toLocaleTimeString(locale)}
        {entry.source !== 'page' && <><br /><span style={{ fontSize: '0.85em' }}>{entry.source}</span></>}
      </span>
      <span style={{ textAlign: 'right', overflowWrap: 'anywhere', color: LOG_COLORS[entry.level] ?? LOG_COLORS.normal }}>
        {entry.text}
      </span>
    </div>
  ));
}

// Which levels the log lists show; one choice for both lists.
export function LogFilter({ value, onChange }) {
  return (
    <label style={styles.infoRow}>
      <span style={styles.infoLabel}>{tr('Niveau')}</span>
      <select value={value ?? 'all'} style={styles.select}
        onChange={(event) => onChange(event.target.value)}>
        {LOG_FILTERS.map((item) => <option key={item.id} value={item.id}>{tr(item.label)}</option>)}
      </select>
    </label>
  );
}
