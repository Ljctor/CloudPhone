// The plugins' options in the options panel: one foldable section per
// plugin, its options by kind (toggle, number, choice, action, buttons,
// dialog, status, grid, log) and the dialog an option opens. What is stored and
// folded is worked out in pluginSettings.ts.
import React, { useEffect, useState } from 'react';
import { InventoryTable } from './InventoryTable';
import { tr } from './i18n';
import { infoRow } from './infoRows';
import { LogFilter, LogList, serverRecords } from './logs';
import { styles } from './styles';
import {
  foldedChange, optionTree, pluginOptionChange, resolved, sectionFoldId, sectionFolded,
} from './pluginSettings';

// The dialog open over the options panel ({ plugin, option } or null);
// closing the panel closes it.
export function usePluginDialog(panel) {
  const [pluginDialog, setPluginDialog] = useState(null);
  useEffect(() => { if (panel !== 'options') setPluginDialog(null); }, [panel]);
  return [pluginDialog, setPluginDialog];
}

// A plugin's options, with foldable sections nested by their depth.
// context, here and below: { settings, updateSettings, openDialog }.
function pluginSections(context, plugin) {
  const { settings, updateSettings } = context;
  const render = ({ section, options, children }) => {
    const items = options.map(([option, index]) => pluginOption(context, plugin, option, index));
    const nested = children.map(render);
    if (!section) return <React.Fragment key="top">{items}{nested}</React.Fragment>;
    const id = sectionFoldId(plugin, section);
    const folded = sectionFolded(settings, id, section);
    return (
      <details key={id} open={!folded} style={styles.pluginSection}
        onToggle={(event) => {
          const now = !event.currentTarget.open;
          if (now !== folded) updateSettings(foldedChange(settings, 'foldedPlugins', id, now));
        }}>
        <summary style={styles.pluginSectionTitle}>
          {section.icon && <img src={resolved(section.icon)} alt="" style={styles.pluginIcon} />}
          {tr(section.label)}
        </summary>
        {items}{nested}
      </details>
    );
  };
  return render(optionTree(plugin.instance.options));
}

function CapturePreview({ option }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(0);
  const examples = (resolved(option.examples) ?? []).filter((example) => example?.url);
  if (!examples.length) return null;
  const example = examples[Math.min(selected, examples.length - 1)];
  return (
    <div>
      <div style={styles.infoRow}>
        <span style={styles.infoLabel}>{tr(option.label ?? 'Capture')}</span>
        <button style={styles.smallButton} onClick={() => setOpen(!open)}>
          {tr(open ? 'Masquer' : 'Voir')}
        </button>
      </div>
      {open && <div style={{ padding: '6px 10px 12px' }}>
        {examples.length > 1 && <div style={{ display: 'flex', gap: 4, overflowX: 'auto', paddingBottom: 6 }}>
          {examples.map((item, index) => <button key={`${item.url}-${index}`} style={styles.smallButton}
            aria-pressed={index === selected} onClick={() => setSelected(index)}>
            {tr(item.label ?? (index === 0 ? 'Capture principale' : `Capture ${index + 1}`))}
          </button>)}
        </div>}
        <a href={example.url} target="_blank" rel="noreferrer" style={styles.link}>
          <img src={example.url} alt={tr(example.label ?? option.label ?? 'Capture')}
            style={{ display: 'block', maxWidth: '100%', maxHeight: 320, width: 'auto', height: 'auto',
              imageRendering: 'pixelated', borderRadius: 4 }} />
          {tr('Ouvrir capture')}
        </a>
        {example.captured && <div style={styles.infoNote}>
          {new Date(example.captured * 1000).toLocaleString()}
        </div>}
      </div>}
    </div>
  );
}

function pluginOption(context, plugin, option, index) {
  const { settings, updateSettings, openDialog } = context;
  const setPluginOption = (id, key, value) => updateSettings(pluginOptionChange(settings, id, key, value));
  const key = `${plugin.id}-${index}`;
  if (!(option.visible?.() ?? true)) return null;
  if (option.type === 'inventory-table') return <InventoryTable key={key} option={option} tr={tr} />;
  if (option.type === 'capture') return <CapturePreview key={key} option={option} />;
  if (option.type === 'toggle') {
    return (
      <label key={key} style={styles.infoRow}>
        <span style={styles.infoLabel}>{tr(option.label)}</span>
        <input type="checkbox" checked={Boolean(settings.plugins?.[plugin.id]?.[option.key])}
          onChange={(event) => setPluginOption(plugin.id, option.key, event.target.checked)} />
      </label>
    );
  }
  if (option.type === 'number') {
    return (
      <label key={key} style={styles.infoRow}>
        <span style={styles.infoLabel}>{tr(option.label)}</span>
        <input type="text" inputMode="numeric" pattern="[0-9]*" maxLength={12} style={styles.numberInput}
          placeholder={resolved(option.placeholder) ?? ''} value={settings.plugins?.[plugin.id]?.[option.key] ?? ''}
          onChange={(event) => setPluginOption(plugin.id, option.key, event.target.value.replace(/\D/g, ''))} />
      </label>
    );
  }
  if (option.type === 'choice') {
    const choices = resolved(option.choices) ?? [];
    return (
      <label key={key} style={styles.infoRow}>
        <span style={styles.infoLabel}>{tr(option.label)}</span>
        <select style={styles.select} disabled={resolved(option.disabled) ?? false}
          value={resolved(option.value) ?? settings.plugins?.[plugin.id]?.[option.key] ?? choices[0]?.value ?? ''}
          onChange={(event) => setPluginOption(plugin.id, option.key, event.target.value)}>
          {choices.map((choice) => (
            <option key={choice.value} value={choice.value}
              style={choice.muted ? { color: styles.infoNote.color } : undefined}>{tr(choice.label)}</option>
          ))}
        </select>
      </label>
    );
  }
  if (option.type === 'action') {
    return (
      <div key={key} style={styles.infoRow}>
        <span style={styles.infoLabel}>{tr(option.label)}</span>
        <button style={styles.panelButton} disabled={option.disabled?.() ?? false}
          onClick={() => Promise.resolve(option.run?.()).catch((error) => console.error(error))}>
          {tr(option.button ?? option.label)}
        </button>
      </div>
    );
  }
  if (option.type === 'buttons') {
    return (
      <div key={key} style={styles.infoRow}>
        <span style={styles.infoLabel}>{tr(option.label)}</span>
        <span style={styles.buttonGroup}>
          {(option.buttons ?? []).map((button) => (
            <button key={button.label} style={styles.smallButton} disabled={button.disabled?.() ?? false}
              onClick={() => Promise.resolve(button.run?.()).catch((error) => console.error(error))}>
              {tr(button.label)}
            </button>
          ))}
        </span>
      </div>
    );
  }
  if (option.type === 'metrics') {
    return <div key={key} role="group" aria-label={tr(option.label)} style={{ display: 'grid',
      gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '6px', marginBottom: '10px' }}>
      {(option.items?.() ?? []).map((item, index) => <div key={index} data-metric={item.key}
        style={{ minWidth: 0, height: '110px', padding: '6px', boxSizing: 'border-box',
          border: '1px solid #455365', borderRadius: '4px', display: 'flex', flexDirection: 'column', gap: '5px' }}>
        <span style={{ color: '#c4cad3', fontSize: '11px', minHeight: '26px' }}>{tr(item.label)}</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontWeight: 600, fontSize: '12px', minWidth: 0 }}>
          {item.icon && <img src={item.icon} alt="" style={{ width: '14px', height: '14px', objectFit: 'contain', imageRendering: 'pixelated' }} />}
          <span>{item.value}</span>
        </span>
        <span style={{ color: '#9aa7b7', fontSize: '10px', overflowWrap: 'anywhere', height: '28px' }}>{item.detail}</span>
      </div>)}
    </div>;
  }
  if (option.type === 'dialog') {
    // select: a radio button before the label, one of a group sharing
    // the stored key (the first of the group when nothing is stored).
    const select = option.select;
    const stored = select && settings.plugins?.[plugin.id]?.[select.key];
    return (
      <div key={key} style={styles.infoRow}>
        {select ? (
          <label style={{ ...styles.infoLabel, display: 'flex', alignItems: 'center', gap: '6px' }}>
            <input type="radio" name={`${plugin.id}-${select.key}`}
              checked={(stored ?? select.default) === select.value}
              disabled={select.disabled?.() ?? false}
              onChange={() => setPluginOption(plugin.id, select.key, select.value)} />
            {tr(option.label)}
          </label>
        ) : <span style={styles.infoLabel}>{tr(option.label)}</span>}
        {/* No button for a row with nothing to configure (options: []). */}
        {(option.tabs?.length || option.options?.length !== 0) && (
          <button style={styles.panelButton} onClick={() => openDialog({ plugin, option })}>
            {tr(option.button ?? 'Configurer')}
          </button>
        )}
      </div>
    );
  }
  if (option.type === 'grid') {
    // Fixed-size cells, so that the shape does not depend on the font:
    // null is not part of the grid (transparent), 'empty' an outlined
    // empty cell, anything else the CSS colour that fills it.
    const rows = option.rows?.() ?? [];
    const columns = Math.max(0, ...rows.map((row) => row.length));
    return (
      <div key={key} style={styles.infoRow}>
        <span style={styles.infoLabel}>{tr(option.label ?? '')}</span>
        <div data-plugin-grid="" role="img" aria-label={tr(option.label ?? '')}
          style={{ ...styles.pluginGrid, gridTemplateColumns: `repeat(${columns}, ${styles.pluginGridCell.width})` }}>
          {rows.flatMap((row, r) => Array.from({ length: columns }, (_, c) => {
            const cell = row[c] ?? null;
            if (cell === null) return <span key={`${r},${c}`} style={styles.pluginGridCell} />;
            return (
              <span key={`${r},${c}`} data-cell={cell === 'empty' ? 'empty' : 'filled'}
                style={{ ...styles.pluginGridCell, ...(cell === 'empty' ? styles.pluginGridEmpty : { background: cell }) }} />
            );
          }))}
        </div>
      </div>
    );
  }
  if (option.type === 'log') {
    // The server's records that match() keeps (all without it), with the
    // level filter shared with the other logs.
    const entries = serverRecords().filter((record) => option.match?.(record) ?? true);
    return (
      <React.Fragment key={key}>
        <LogFilter value={settings.logFilter} onChange={(logFilter) => updateSettings({ logFilter })} />
        <LogList entries={entries} filter={settings.logFilter} rowStyle={styles.infoRow} labelStyle={styles.infoLabel} />
      </React.Fragment>
    );
  }
  if (option.type === 'status') {
    const value = statusValue(option.value?.() ?? '–', option.look);
    const href = option.href?.();
    const linked = href ? <a href={href} target="_blank" rel="noreferrer" style={styles.link}>{value}</a> : value;
    // muted(): a value not checked lately, greyed.
    const color = resolved(option.color) ?? (option.muted?.() ? styles.infoNote.color : undefined);
    const shown = color ? <span data-muted={option.muted?.() || undefined} style={{ color }}>{linked}</span> : linked;
    const timestamp = resolved(option.timestamp);
    // Inline buttons after the value, while button() gives one (or a list).
    const given = option.button?.();
    const buttons = (Array.isArray(given) ? given : [given]).filter(Boolean);
    if ((option.compact || option.timestamp) && !buttons.length) return (
      <div key={key} title={resolved(option.title) ?? ''}
        style={{ ...styles.infoRow, display: 'grid', alignItems: 'center', minWidth: 0,
          gridTemplateColumns: option.compact
            ? 'minmax(0, 1fr) 14px minmax(0, 9ch) 5ch' : 'minmax(0, 1fr) 14px minmax(0, auto) 5ch',
          columnGap: 6 }}>
        <span style={{ ...styles.infoLabel, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {tr(option.label)}
        </span>
        <span style={{ width: 14, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
          {option.icon && <img src={resolved(option.icon)} alt="" style={{ width: 14, height: 14,
            objectFit: 'contain', imageRendering: 'pixelated' }} />}
        </span>
        <span style={{ minWidth: 0, textAlign: 'right', overflowWrap: 'anywhere',
          color: color ?? '#fff', fontVariantNumeric: 'tabular-nums' }}>{shown}</span>
        <span data-timestamp="true" style={{ color: styles.infoNote.color, textAlign: 'right',
          whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums', fontSize: '0.85em' }}>{timestamp}</span>
      </div>
    );
    return infoRow(tr(option.label), buttons.length ? (
      <>
        {shown}
        {buttons.map((button) => (
          <React.Fragment key={button.label}>
            {' '}
            <button style={styles.smallButton}
              onClick={() => Promise.resolve(button.run?.()).catch((error) => console.error(error))}>
              {tr(button.label)}
            </button>
          </React.Fragment>
        ))}
      </>
    ) : shown);
  }
  return null;
}

// A status value: a text, or parts (a text, or { icon, text }: the icon
// before its text); look 'game': white with a black outline.
function statusValue(value, look) {
  const parts = Array.isArray(value)
    ? value.map((part, index) => (typeof part === 'string' ? <React.Fragment key={index}>{part}</React.Fragment> : (
      <span key={index} style={styles.statusPart}>
        {part.icon && <img src={part.icon} alt="" style={part.size
          ? { ...styles.statusIcon, width: part.size, height: part.size, objectFit: 'contain' } : styles.statusIcon} />}
        {part.color ? <span style={{ color: part.color }}>{part.text}</span> : part.text}
      </span>
    )))
    : value;
  return look === 'game' ? <span style={styles.gameText}>{parts}</span> : parts;
}

export function PluginList({ plugins, settings, updateSettings, openDialog }) {
  const context = { settings, updateSettings, openDialog };
  return (
    <>
      <div style={styles.infoSection}>{tr('Plugins')}</div>
      {plugins.length === 0 && <div style={styles.infoNote}>{tr('Aucun plugin installé.')}</div>}
      {plugins.map((plugin) => (
        // One foldable section per plugin, folded state kept with the settings.
        <details key={plugin.id} open={!settings.foldedPlugins?.[plugin.id]}
          onToggle={(event) => {
            const folded = !event.currentTarget.open;
            if (folded !== Boolean(settings.foldedPlugins?.[plugin.id])) {
              updateSettings(foldedChange(settings, 'foldedPlugins', plugin.id, folded));
            }
          }}>
          <summary style={styles.pluginTitle}>
            {plugin.instance?.icon && <img src={plugin.instance.icon} alt="" style={styles.pluginIcon} />}
            {plugin.title}
          </summary>
          {plugin.error && <div style={styles.infoWarning}>{tr('Échec : {message}', { message: plugin.error })}</div>}
          {pluginSections(context, plugin)}
        </details>
      ))}
    </>
  );
}

export function PluginDialog({ dialog, settings, updateSettings, openDialog }) {
  const context = { settings, updateSettings, openDialog };
  const tabs = dialog.option.tabs ?? [];
  const [selected, setSelected] = useState(dialog.option.initialTab ?? tabs[0]?.id);
  useEffect(() => { setSelected(dialog.option.initialTab ?? tabs[0]?.id); }, [dialog.option]);
  const active = tabs.find((tab) => tab.id === selected) ?? tabs[0];
  const activate = (id) => { setSelected(id); };
  return (
    <div style={styles.pluginDialog} role="dialog" aria-label={tr(dialog.option.title ?? dialog.option.label)}>
      <div style={styles.infoHeader}>
        <strong>{tr(dialog.option.title ?? dialog.option.label)}</strong>
        <button style={styles.infoClose} onClick={() => openDialog(null)} aria-label={tr('Fermer')}>✕</button>
      </div>
      {tabs.length > 0 && <div role="tablist" aria-label={tr(dialog.option.title ?? dialog.option.label)}
        style={{ display: 'grid', gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))`, gap: '4px', flexShrink: 0, paddingBottom: '8px' }}>
        {tabs.map((tab, index) => <button key={tab.id} id={`plugin-tab-${tab.id}`} role="tab"
          aria-selected={active?.id === tab.id} aria-controls={`plugin-panel-${tab.id}`}
          tabIndex={active?.id === tab.id ? 0 : -1}
          style={{ ...styles.smallButton, minWidth: 0, padding: '4px 2px', fontSize: '11px', minHeight: '44px',
            borderColor: active?.id === tab.id ? '#5abfff' : '#536174',
            background: active?.id === tab.id ? '#304f6b' : '#28313e' }}
          onClick={() => activate(tab.id)} onKeyDown={(event) => {
            const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length
              : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length
                : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : null;
            if (next !== null) { event.preventDefault(); activate(tabs[next].id);
              event.currentTarget.parentElement?.querySelectorAll('button')[next]?.focus(); }
          }}>{tr(tab.label)}</button>)}
      </div>}
      <div role={active ? 'tabpanel' : undefined} id={active ? `plugin-panel-${active.id}` : undefined}
        aria-labelledby={active ? `plugin-tab-${active.id}` : undefined}>
        {(active?.options ?? dialog.option.options ?? []).map((option, index) => pluginOption(context, dialog.plugin, option, `dialog-${active?.id ?? ''}-${index}`))}
      </div>
    </div>
  );
}
