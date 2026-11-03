// The status diagnose() picks, as the page shows it: covering the screen
// while it is blocking (or the video is not there yet), otherwise as a
// closable banner over the video. Each new status also goes to the page's
// log.
import { useEffect, useState } from 'react';
import { tr } from './i18n';
import { bannerShown, problemKey, problemLogEntry } from './diagnose';
import { pageLog } from './logs';
import { LEVEL_COLORS, styles } from './styles';

// The text of the closed banner: a closed warning stays hidden until it
// goes away and comes back.
export function useDismissed(problem) {
  const [dismissed, setDismissed] = useState(null);
  useEffect(() => {
    if (dismissed !== null && problemKey(problem) !== dismissed) setDismissed(null);
    if (problem) pageLog(...problemLogEntry(problem));
  }, [problemKey(problem)]);
  return [dismissed, setDismissed];
}

// Recovery and Options remain in the existing toolbar, above this cover.
export function StatusCover({ problem, stream }) {
  if (stream === 'connected' && !problem?.blocking) return null;
  return (
    <div style={styles.loading} data-cloudphone-notice="cover" role="status" aria-live="polite">
      {problem?.blocking && problem.level === 'error'
        ? <span style={{ ...styles.problemMark, color: LEVEL_COLORS.error }} aria-hidden="true">!</span>
        : <span style={styles.spinner} aria-hidden="true" />}
      <span style={styles.loadingText}>
        {problem?.blocking ? tr(problem.text, problem.params) : tr('Connexion au serveur…')}
      </span>
      {problem?.blocking && problem.detail && <span style={styles.loadingDetail}>{tr(problem.detail)}</span>}
    </div>
  );
}

export function Banner({ problem, dismissed, dismiss }) {
  if (!bannerShown(problem, dismissed)) return null;
  return (
    <div style={{ ...styles.banner, ...styles.bannerWithClose, borderColor: LEVEL_COLORS[problem.level] }}
      data-cloudphone-notice="banner" role="status">
      <span>{tr(problem.text, problem.params)}{problem.detail && <><br /><small>{tr(problem.detail)}</small></>}</span>
      <button style={styles.bannerClose} onClick={() => dismiss(problemKey(problem))}
        aria-label={tr('Fermer')}>✕</button>
    </div>
  );
}
