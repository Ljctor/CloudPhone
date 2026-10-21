// One log, two outputs: the page's own records (Client tab) and the
// server's (GET /api/v1/logs, Server tab), both newest first. Records with
// notify also show as toasts. The page's warnings and errors also go to the
// browser's console at their level. See logRecords.ts for the records.
import { useEffect, useRef, useState } from 'react';
import { language, tr } from './i18n';
import { VIEWER_ID } from './api';
import { styles } from './styles';
import {
  LOG_COLORS, LOG_FILTERS, TOAST_MS, keepRecord, shownRecords, toastKey, withToast,
} from './logRecords';

const PAGE_LOG = [];
const SERVER_LOG = [];
const logListeners = new Set();
const toastListeners = new Set();
const CONSOLE = { warning: console.warn.bind(console), error: console.error.bind(console) };

function logChanged() {
  logListeners.forEach((listener) => listener());
}

export function pageLog(level, text, { notify = false, toConsole = true } = {}) {
  const record = { time: Date.now() / 1000, level, source: 'page', text, ...(notify ? { notify: true } : {}) };
  keepRecord(PAGE_LOG, record);
  if (toConsole) CONSOLE[level]?.(text);
  if (notify) toastListeners.forEach((listener) => listener(record));
  logChanged();
}

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

// Reads the server's new records every few seconds, whatever is open: the
// first answer fills the list, later ones also raise toasts. A restarted
// gateway answers an old cursor with all its records.
const SERVER_LOG_MS = 4000;
export function useServerLog(gatewayUrl) {
  useEffect(() => {
    let cancelled = false;
    let cursor = '';
    let first = true;
    const load = () => fetch(`${gatewayUrl}/api/v1/logs?since=${encodeURIComponent(cursor)}`, { cache: 'no-store' })
      .then((response) => (response.ok ? response.json() : null))
      .then((value) => {
        if (cancelled || !value) return;
        cursor = value.cursor ?? '';
        const records = value.records ?? [];
        records.forEach((record) => {
          keepRecord(SERVER_LOG, record);
          if (!first && record.notify && record.params?.viewer !== VIEWER_ID) {
            toastListeners.forEach((listener) => listener(record));
          }
        });
        first = false;
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

// Toasts for notify records, from both sides. While the tab is hidden, a
// system notification too, only if the user already allowed them for this
// page (the page never asks).
export function useToasts() {
  const [toasts, setToasts] = useState([]);
  const timers = useRef(new Map());
  const dismiss = (key) => {
    window.clearTimeout(timers.current.get(key));
    timers.current.delete(key);
    setToasts((list) => list.filter((toast) => toast.key !== key));
  };
  useEffect(() => {
    const show = (record) => {
      const text = record.text;
      const key = toastKey(record, text);
      setToasts((list) => withToast(list, record, text));
      window.clearTimeout(timers.current.get(key));
      if (TOAST_MS[record.level]) timers.current.set(key, window.setTimeout(() => dismiss(key), TOAST_MS[record.level]));
      if (document.visibilityState === 'hidden' && typeof Notification !== 'undefined'
        && Notification.permission === 'granted') {
        try {
          new Notification('Cloud Phone', { body: text, tag: key });
        } catch {
          // Some mobile browsers only notify from a service worker.
        }
      }
    };
    toastListeners.add(show);
    return () => {
      toastListeners.delete(show);
      timers.current.forEach((timer) => window.clearTimeout(timer));
    };
  }, []);
  return [toasts, dismiss];
}

export function Toasts({ toasts, dismiss, top }) {
  if (toasts.length === 0) return null;
  return (
    <div style={{ ...styles.toasts, top }} aria-label={tr('Notifications')} aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.key} style={{ ...styles.toast, borderLeft: `4px solid ${LOG_COLORS[toast.level]}` }}
          data-toast={toast.level}>
          <span style={{ color: LOG_COLORS[toast.level] }}>
            {toast.text}{toast.count > 1 && <small style={styles.toastCount}> ×{toast.count}</small>}
          </span>
          <button style={styles.bannerClose} onClick={() => dismiss(toast.key)}
            aria-label={tr('Fermer la notification')}>✕</button>
        </div>
      ))}
    </div>
  );
}
