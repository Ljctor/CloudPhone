// Which panel is open over the screen: 'info' (from the ping/fps block,
// with a client and a server tab) or 'options' (from the cog), or none;
// and what the polls that run only while a panel shows need to know.
import { useState } from 'react';

export function usePanels() {
  const [panel, setPanel] = useState(null);
  const [infoTab, setInfoTab] = useState('client');
  // The polls: the server's state and settings while the server tab shows,
  // the logs while information is open, the alerts while options are.
  const serverTab = panel === 'info' && infoTab === 'server';
  const infoOpen = panel === 'info';
  const optionsOpen = panel === 'options';
  const togglePanel = (name) => setPanel((open) => (open === name ? null : name));
  // Information opens on the client tab.
  const openInfo = () => {
    if (panel !== 'info') setInfoTab('client');
    togglePanel('info');
  };
  return { panel, setPanel, infoTab, setInfoTab, serverTab, infoOpen, optionsOpen, togglePanel, openInfo };
}
