// Which panel is open over the screen: 'info' (from the ping/fps block,
// with a client and a server tab) or 'options' (from the cog), or none.
import { useState } from 'react';

export function usePanels() {
  const [panel, setPanel] = useState(null);
  const [infoTab, setInfoTab] = useState('client');
  const serverTab = panel === 'info' && infoTab === 'server';
  const togglePanel = (name) => setPanel((open) => (open === name ? null : name));
  // Information opens on the client tab.
  const openInfo = () => {
    if (panel !== 'info') setInfoTab('client');
    togglePanel('info');
  };
  return { panel, setPanel, infoTab, setInfoTab, serverTab, togglePanel, openInfo };
}
