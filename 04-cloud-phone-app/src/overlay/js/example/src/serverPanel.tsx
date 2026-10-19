// The information panel's Server tab: the server's state and metrics
// (serverInfo.ts makes the rows), disconnecting the other viewers, the
// Android settings form and the server's log.
import { tr } from './i18n';
import { VIEWER_ID, postFetch, postHeaders } from './api';
import { styles } from './styles';

function disconnectOthers(gatewayUrl) {
  return postFetch(`${gatewayUrl}/api/v1/viewers/disconnect-others`, {
    method: 'POST',
    headers: postHeaders(),
    body: JSON.stringify({ viewer: VIEWER_ID }),
  }).catch((error) => console.error('Disconnect others:', error));
}

// sections: the rendered rows; viewers: how many are connected;
// settingsForm and logs: the form and the log list, rendered by the page.
export function ServerPanel({ sections, viewers, gatewayUrl, settingsForm, logs }) {
  return (
    <div role="tabpanel">
      {sections}
      {viewers > 1 && (
        <div style={styles.infoRow}>
          <span style={styles.infoLabel}>{tr('Autres appareils')}</span>
          <button style={styles.panelButton} onClick={() => disconnectOthers(gatewayUrl)}>
            {tr('Déconnecter')}
          </button>
        </div>
      )}
      <div style={styles.infoSection}>{tr('Réglages d’Android')}</div>
      {settingsForm}
      {logs}
    </div>
  );
}
