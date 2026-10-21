// Phone alerts through ntfy.sh (GET/POST /api/v1/notify): the options
// panel's "Alertes sur le téléphone" section.
import { useEffect, useState } from 'react';
import { tr } from './i18n';
import { postFetch, postHeaders } from './api';
import { Icon } from './icons';
import { styles } from './styles';

// Copies text. The page is often served over plain http (through
// WireGuard), where navigator.clipboard does not exist: then through a
// hidden text field and the older copy command.
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const field = document.createElement('textarea');
    field.value = text;
    field.setAttribute('readonly', '');
    field.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
    document.body.appendChild(field);
    field.select();
    field.setSelectionRange(0, text.length);
    let done = false;
    try {
      done = document.execCommand('copy');
    } catch {
      done = false;
    }
    field.remove();
    return done;
  }
}

// The alerts' state, read while the options panel is open (enabled), and
// the section's own: its last note and whether the address was just copied.
// Kept by the page, so they outlive a closed panel.
export function useAlerts(gatewayUrl, enabled) {
  const [value, setValue] = useState(null);
  const [note, setNote] = useState('');
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    fetch(`${gatewayUrl}/api/v1/notify`, { cache: 'no-store' })
      .then((response) => (response.ok ? response.json() : null))
      .then((next) => { if (!cancelled) setValue(next); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [gatewayUrl, enabled]);
  const change = async (body) => {
    const response = await postFetch(`${gatewayUrl}/api/v1/notify`, {
      method: 'POST', headers: postHeaders(), body: JSON.stringify(body),
    }).catch(() => null);
    if (response?.ok) setValue(await response.json());
    return Boolean(response?.ok);
  };
  const test = async () => {
    const response = await postFetch(`${gatewayUrl}/api/v1/notify/test`, {
      method: 'POST', headers: postHeaders(), body: '{}',
    }).catch(() => null);
    return Boolean(response?.ok);
  };
  return { value, change, test, note, setNote, copied, setCopied };
}

export function AlertsPanel({ alerts }) {
  const { note, setNote, copied, setCopied } = alerts;
  return (
    <>
      <div style={styles.infoSection}>{tr('Alertes sur le téléphone')}</div>
      {alerts.value && !alerts.value.available && (
        <div style={styles.infoNote}>{tr('Non disponibles sur ce serveur.')}</div>
      )}
      {alerts.value?.available && (
        <>
          <label style={styles.infoRow}>
            <span style={styles.infoLabel}>{tr('Alertes par ntfy (même page fermée)')}</span>
            <input type="checkbox" checked={alerts.value.enabled}
              onChange={(event) => { setNote(''); alerts.change({ enabled: event.target.checked }); }} />
          </label>
          {alerts.value.enabled && alerts.value.url && (
            <>
              {/* The link itself is shown only when it could not be copied. */}
              <div style={styles.infoRow}>
                <span style={styles.infoLabel}>{tr('Lien topic ntfy')}</span>
                <button style={styles.iconButton} aria-label={tr('Copier le lien')} title={tr('Copier le lien')}
                  onClick={async () => {
                    const done = await copyText(alerts.value.url);
                    setCopied(done);
                    setNote(done ? '' : 'copy-failed');
                    if (done) window.setTimeout(() => setCopied(false), 2000);
                  }}>
                  <Icon name={copied ? 'check' : 'copy'} />
                </button>
              </div>
              <div style={styles.infoRow}>
                <span style={styles.infoLabel}>{tr('Alerte de test')}</span>
                <button style={styles.panelButton} onClick={async () => {
                  setNote(await alerts.test() ? tr('Envoyée.') : tr('Échec de l’envoi.'));
                }}>{tr('Envoyer')}</button>
              </div>
              <div style={styles.infoNote}>
                {tr('ntfy est une app de notifications (Android, iOS, web). Installe-la, touche + et colle le lien.')}
              </div>
            </>
          )}
          {note === 'copy-failed' && alerts.value.url && (
            <div style={styles.infoNote}>
              {tr('Copie impossible : touche longuement le lien.')}{' '}
              <a href={alerts.value.url} target="_blank" rel="noreferrer" style={styles.link}>
                {alerts.value.url.replace(/^https:\/\//, '')}
              </a>
            </div>
          )}
          {note && note !== 'copy-failed' && <div style={styles.infoNote}>{note}</div>}
        </>
      )}
    </>
  );
}
