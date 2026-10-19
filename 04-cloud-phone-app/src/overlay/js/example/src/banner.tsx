// The status diagnose() picks, as the page shows it: covering the screen
// while it is blocking (or the video is not there yet), otherwise as a
// closable banner over the video. Each new status also goes to the page's
// log.
import { useEffect, useState } from 'react';
import { tr } from './i18n';
import { bannerShown, problemLogEntry } from './diagnose';
import { pageLog } from './logs';
import { styles } from './styles';

export const LEVEL_COLORS = { error: '#ff453a', wait: '#ff9f0a', info: '#ffd60a' };

// The text of the closed banner: a closed warning stays hidden until it
// goes away and comes back.
export function useDismissed(problem) {
  const [dismissed, setDismissed] = useState(null);
  useEffect(() => {
    if (dismissed !== null && problem?.text !== dismissed) setDismissed(null);
    if (problem) pageLog(...problemLogEntry(problem));
  }, [problem?.text]);
  return [dismissed, setDismissed];
}

// stream: the video's state; reconnecting: the user asked for a new one.
export function StatusCover({ problem, stream, reconnecting }) {
  if (stream === 'connected' && !problem?.blocking) return null;
  return (
    <div style={styles.loading} role="status" aria-live="polite">
      {problem?.blocking && problem.level === 'error'
        ? <span style={{ ...styles.problemMark, color: LEVEL_COLORS.error }} aria-hidden="true">!</span>
        : <span style={styles.spinner} aria-hidden="true" />}
      <span style={styles.loadingText}>
        {problem?.blocking ? tr(problem.text) : reconnecting ? tr('Reconnexion…') : tr('Connexion au flux…')}
      </span>
      {problem?.blocking && problem.detail && <span style={styles.loadingDetail}>{tr(problem.detail)}</span>}
    </div>
  );
}

export function Banner({ problem, dismissed, dismiss }) {
  if (!bannerShown(problem, dismissed)) return null;
  return (
    <div style={{ ...styles.banner, ...styles.bannerWithClose, borderColor: LEVEL_COLORS[problem.level] }}
      role="status">
      <span>{tr(problem.text)}{problem.detail && <><br /><small>{tr(problem.detail)}</small></>}</span>
      <button style={styles.bannerClose} onClick={() => dismiss(problem.text)}
        aria-label={tr('Fermer')}>✕</button>
    </div>
  );
}
