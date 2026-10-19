// The page's inline styles, one object for every component.

export const TOOLBAR_WIDTH = 40;

// A status's colour by level (diagnose.ts): the banner's border, the LED.
export const LEVEL_COLORS = { error: '#ff453a', wait: '#ff9f0a', info: '#ffd60a' };

export const styles = {
  // The screen and the toolbar form one centered block, so on a wide window
  // the toolbar stays next to the screen instead of at the window's edge.
  app: {
    position: 'fixed', inset: 0, display: 'flex', flexDirection: 'row',
    alignItems: 'center', justifyContent: 'center',
    overflow: 'hidden', background: '#20242b', color: '#fff', touchAction: 'none',
  },
  screen: {
    flex: '0 0 auto', display: 'flex', alignItems: 'center',
    justifyContent: 'center', overflow: 'hidden', background: '#20242b',
  },
  device: { position: 'relative', flex: '0 0 auto', background: '#000' },
  loading: {
    position: 'absolute', inset: 0, zIndex: 3, display: 'flex', flexDirection: 'column',
    alignItems: 'center', justifyContent: 'center', gap: '12px', background: '#20242b',
  },
  spinner: {
    width: '34px', height: '34px', boxSizing: 'border-box', borderRadius: '50%',
    border: '4px solid #525964', borderTopColor: '#4da3ff',
    animation: 'stream-spinner 0.8s linear infinite',
  },
  loadingText: {
    color: '#d8dde5', fontSize: '13px', fontFamily: 'system-ui, sans-serif',
  },
  pluginLayer: { position: 'absolute', inset: 0, zIndex: 1, pointerEvents: 'none' },
  // A plugin's dialog, over the options panel.
  pluginDialog: {
    position: 'absolute', left: '20px', right: '20px', top: '48px', zIndex: 5,
    maxHeight: 'calc(100% - 64px)', overflowY: 'auto', touchAction: 'pan-y', boxSizing: 'border-box',
    padding: '10px 12px', borderRadius: '10px', background: '#1c1f26',
    border: '1px solid #4a505a', boxShadow: '0 8px 24px rgba(0, 0, 0, 0.6)',
    fontFamily: 'system-ui, sans-serif', fontSize: '13px', display: 'flex', flexDirection: 'column', gap: '4px',
  },
  pluginSection: { marginLeft: '10px' },
  pluginSectionTitle: { marginTop: '4px', color: '#c4cad3', fontWeight: 600, cursor: 'pointer' },
  pluginTitle: { marginTop: '6px', fontWeight: 600, cursor: 'pointer' },
  numberInput: {
    width: '96px', padding: '3px 6px', borderRadius: '6px', border: '1px solid #3a3f47',
    background: '#1b1d22', color: '#e8ebf0', font: 'inherit', textAlign: 'right',
  },
  tabs: { display: 'flex', gap: '6px', margin: '4px 0 6px' },
  tab: {
    flex: 1, padding: '5px 0', borderRadius: '6px', border: '1px solid #3a3f47',
    background: 'transparent', color: '#c9ced6', font: 'inherit', cursor: 'pointer',
  },
  tabSelected: { background: '#3a6ea5', borderColor: '#4da3ff', color: '#fff' },
  touchMarker: {
    position: 'absolute', left: '-14px', top: '-14px', width: '28px', height: '28px', zIndex: 2,
    borderRadius: '50%', background: 'rgba(77, 163, 255, 0.35)', border: '2px solid rgba(77, 163, 255, 0.8)',
    boxSizing: 'border-box', pointerEvents: 'none', opacity: 0, transition: 'opacity 0.15s',
  },
  touchLayer: {
    position: 'absolute', inset: 0, zIndex: 2, touchAction: 'none', cursor: 'default',
  },
  toolbar: {
    flex: `0 0 ${TOOLBAR_WIDTH}px`, alignSelf: 'stretch', width: `${TOOLBAR_WIDTH}px`,
    boxSizing: 'border-box', display: 'grid', gridTemplateRows: 'auto 1fr auto',
    justifyItems: 'center', rowGap: '8px', padding: '6px 2px',
    background: '#1b1d22', borderLeft: '1px solid #3b3f47', zIndex: 10,
  },
  toolbarOverlay: {
    position: 'fixed', left: 0, right: 0, bottom: 0, width: '100%',
    background: 'rgba(27, 29, 34, 0.85)', borderTop: '1px solid rgba(59, 63, 71, 0.85)',
  },
  toolbarHandle: {
    position: 'fixed', zIndex: 11, touchAction: 'none',
    width: '36px', height: '36px', padding: 0, display: 'flex', alignItems: 'center',
    justifyContent: 'center', border: '1px solid rgba(85, 85, 85, 0.8)',
    borderRadius: '50%', background: 'rgba(27, 29, 34, 0.7)', color: '#d8dde5',
    boxShadow: '0 1px 4px rgba(0, 0, 0, 0.5)',
  },
  // Horizontal bar: left, centre and right zones; the centre stays centred
  // whatever the side zones hold.
  toolbarBar: {
    flex: `0 0 ${TOOLBAR_WIDTH}px`, alignSelf: 'stretch', height: `${TOOLBAR_WIDTH}px`,
    boxSizing: 'border-box', display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto minmax(0, 1fr)',
    alignItems: 'center', columnGap: '4px', padding: '2px 4px',
    background: '#1b1d22', borderTop: '1px solid #3b3f47', zIndex: 10,
  },
  barZone: { display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '2px', minWidth: 0 },
  barZoneColumn: { flexDirection: 'column', gap: '6px', minHeight: 0 },
  // Every button has the same size; below the screen they are a bit smaller
  // so the whole bar fits a narrow phone.
  buttonBelow: { flex: '0 0 28px', width: '28px', minWidth: '28px', height: '28px' },
  metric: {
    flex: '0 0 auto', minWidth: '28px', minHeight: '28px', margin: 0, padding: '1px 2px',
    border: 'none', background: 'transparent', color: '#e8ebf0', cursor: 'pointer',
    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
    fontFamily: 'system-ui, sans-serif', fontVariantNumeric: 'tabular-nums', touchAction: 'manipulation',
  },
  metricLine: { fontSize: '10px', lineHeight: 1.2, whiteSpace: 'nowrap', overflow: 'hidden' },
  withLed: { position: 'relative' },
  led: {
    position: 'absolute', top: '3px', right: '3px', width: '7px', height: '7px',
    borderRadius: '50%', boxShadow: '0 0 0 1px #1b1d22',
  },
  // Stays at the top while the panel scrolls, so the close button is always
  // in reach.
  infoHeader: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px',
    position: 'sticky', top: '-10px', zIndex: 1, margin: '-10px -12px 4px', padding: '10px 12px 6px',
    background: 'rgba(20, 22, 27, 0.98)', borderRadius: '10px 10px 0 0',
  },
  infoClose: {
    width: '26px', height: '26px', padding: 0, border: '1px solid #444', borderRadius: '7px',
    background: '#292929', color: '#fff', fontSize: '13px',
  },
  infoSection: { marginTop: '8px', marginBottom: '2px', color: '#d8dde5', fontWeight: 600 },
  infoNote: { marginTop: '4px', color: '#8a919c', fontSize: '11px', lineHeight: 1.35 },
  infoWarning: { marginTop: '4px', color: '#ff9f0a', fontSize: '12px', lineHeight: 1.35 },
  select: {
    maxWidth: '60%', padding: '3px 4px', borderRadius: '6px', border: '1px solid #444',
    background: '#292929', color: '#e8ebf0', fontSize: '12px',
  },
  buttonGroup: { display: 'flex', flexWrap: 'wrap', gap: '4px', justifyContent: 'flex-end' },
  smallButton: {
    minWidth: '34px', padding: '4px 6px', borderRadius: '7px', border: '1px solid #4da3ff',
    background: '#2f5d8f', color: '#fff', fontSize: '12px',
  },
  link: { color: '#8cc4ff', wordBreak: 'break-all' },
  copyRow: { display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 },
  iconButton: {
    flex: 'none', width: '30px', height: '30px', padding: '3px', borderRadius: '7px',
    border: '1px solid #4da3ff', background: '#2f5d8f', color: '#fff',
  },
  panelButton: {
    padding: '4px 10px', borderRadius: '7px', border: '1px solid #4da3ff',
    background: '#2f5d8f', color: '#fff', fontSize: '12px',
  },
  problemMark: {
    width: '34px', height: '34px', borderRadius: '50%', border: '3px solid currentColor',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: '20px', fontWeight: 700, fontFamily: 'system-ui, sans-serif', boxSizing: 'border-box',
  },
  loadingDetail: {
    maxWidth: '80%', color: '#8a919c', fontSize: '12px', textAlign: 'center',
    fontFamily: 'system-ui, sans-serif', lineHeight: 1.35,
  },
  banner: {
    position: 'absolute', left: '50%', top: '8px', transform: 'translateX(-50%)', zIndex: 3,
    padding: '10px 14px', borderRadius: '10px', background: 'rgba(20, 22, 27, 0.92)',
    border: '1px solid #3b3f47', color: '#e8ebf0', fontFamily: 'system-ui, sans-serif',
    fontSize: '13px', textAlign: 'center', maxWidth: '80%', boxSizing: 'border-box',
  },
  // In the corner, with the same padding on both sides: the text stays
  // centred.
  bannerWithClose: { padding: '10px 28px' },
  // Over the screen only (never the toolbar), above the panels; only the
  // toasts themselves take touches.
  toasts: {
    position: 'absolute', left: '8px', right: '8px', zIndex: 6, pointerEvents: 'none',
    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px',
  },
  toast: {
    position: 'relative', pointerEvents: 'auto', maxWidth: '100%', boxSizing: 'border-box',
    padding: '8px 30px 8px 12px', borderRadius: '8px', background: 'rgba(20, 22, 27, 0.94)',
    border: '1px solid #3b3f47', fontFamily: 'system-ui, sans-serif',
    fontSize: '13px', lineHeight: 1.35, boxShadow: '0 4px 14px rgba(0, 0, 0, 0.5)', overflowWrap: 'anywhere',
  },
  toastCount: { color: '#8a919c' },
  bannerClose: {
    position: 'absolute', top: '4px', right: '4px',
    width: '22px', height: '22px', padding: 0, border: 'none',
    background: 'transparent', color: '#8a919c', fontSize: '14px', lineHeight: 1,
  },
  info: {
    position: 'absolute', left: '8px', right: '8px', top: '8px', zIndex: 4,
    maxHeight: 'calc(100% - 16px)', overflowY: 'auto', touchAction: 'pan-y', boxSizing: 'border-box',
    padding: '10px 12px', borderRadius: '10px', background: 'rgba(20, 22, 27, 0.92)',
    border: '1px solid #3b3f47', fontFamily: 'system-ui, sans-serif', fontSize: '13px',
    display: 'flex', flexDirection: 'column', gap: '4px',
  },
  infoRow: { display: 'flex', justifyContent: 'space-between', gap: '12px' },
  infoLabel: { color: '#8a919c' },
  button: {
    flex: '0 0 34px', width: '34px', height: '34px', minWidth: '34px', margin: 0, padding: 0,
    border: '1px solid #444', borderRadius: '9px', background: '#292929', color: '#fff',
    display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '22px', lineHeight: 1, fontFamily: 'system-ui, sans-serif', touchAction: 'manipulation',
  },
  buttonBusy: { background: '#2f5d8f', borderColor: '#4da3ff' },
  buttonDocked: { borderColor: '#4da3ff' },
  icon: { display: 'block', margin: 'auto' },
  // A steady rotation of the centred icon, slow enough to read as "working".
  spinningIcon: {
    display: 'block', margin: 'auto', transformOrigin: '50% 50%',
    animation: 'stream-spinner 1.2s linear infinite',
  },
};
