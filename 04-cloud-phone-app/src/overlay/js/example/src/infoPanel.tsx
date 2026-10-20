// The frame of the panel open over the screen: its title and close button,
// and for Information the client and server tabs; the content is given.
import { tr } from './i18n';
import { styles } from './styles';

export function InfoPanel({ panel, infoTab, setInfoTab, close, children }) {
  const title = panel === 'info' ? tr('Informations') : tr('Options');
  return (
    <div style={styles.info} role="dialog" aria-label={title}>
      <div style={styles.infoHeader}>
        <strong>{title}</strong>
        <button style={styles.infoClose} onClick={close} aria-label={tr('Fermer')}>✕</button>
      </div>
      {panel === 'info' && (
        <div style={styles.tabs} role="tablist">
          {[['client', tr('Client')], ['server', tr('Serveur')]].map(([id, label]) => (
            <button key={id} role="tab" aria-selected={infoTab === id}
              style={infoTab === id ? { ...styles.tab, ...styles.tabSelected } : styles.tab}
              onClick={() => setInfoTab(id)}>{label}</button>
          ))}
        </div>
      )}
      {children}
    </div>
  );
}
