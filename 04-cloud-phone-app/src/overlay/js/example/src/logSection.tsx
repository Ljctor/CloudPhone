// A log in the information panel: a section that folds under its title,
// folded at first, with the level filter and the records. The folded state
// and the filter are kept with the other settings.
import { tr } from './i18n';
import { LogFilter, LogList } from './logs';
import { sectionFolded } from './pageSettings';
import { foldedChange } from './pluginSettings';
import { styles } from './styles';

// id: the folded state's key; title: French source text.
export function LogSection({ id, title, entries, settings, updateSettings }) {
  const folded = sectionFolded(settings, id);
  return (
    <details open={!folded} onToggle={(event) => {
      const now = !event.currentTarget.open;
      if (now !== folded) updateSettings(foldedChange(settings, 'foldedSections', id, now));
    }}>
      <summary style={{ ...styles.infoSection, cursor: 'pointer' }}>{tr(title)}</summary>
      {!folded && (
        <>
          <LogFilter value={settings.logFilter} onChange={(logFilter) => updateSettings({ logFilter })} />
          <LogList entries={entries} filter={settings.logFilter} rowStyle={styles.infoRow}
            labelStyle={styles.infoLabel} />
        </>
      )}
    </details>
  );
}
