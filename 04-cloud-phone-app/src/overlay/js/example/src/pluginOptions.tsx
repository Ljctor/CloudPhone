// The plugins' options in the options panel: one foldable section per
// plugin, its options by kind (toggle, number, choice, action, buttons,
// dialog, status, grid, log) and the dialog an option opens. What is stored and
// folded is worked out in pluginSettings.ts.
import React, { useEffect, useState } from 'react';
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
        <select style={styles.select} value={settings.plugins?.[plugin.id]?.[option.key] ?? choices[0]?.value ?? ''}
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
        {option.options?.length !== 0 && (
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
    const shown = option.muted?.() ? <span data-muted="true" style={{ color: styles.infoNote.color }}>{linked}</span> : linked;
    // Inline buttons after the value, while button() gives one (or a list).
    const given = option.button?.();
    const buttons = (Array.isArray(given) ? given : [given]).filter(Boolean);
    if (option.compact && !buttons.length) return (
      <div key={key} title={resolved(option.title) ?? ''}
        style={{ ...styles.infoRow, alignItems: 'center', minWidth: 0, whiteSpace: 'nowrap' }}>
        <span style={{ ...styles.infoLabel, display: 'inline-flex', alignItems: 'center', minWidth: 0,
          overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {tr(option.label)}
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, flexShrink: 0,
          color: '#fff', fontVariantNumeric: 'tabular-nums' }}>
          {option.icon && <img src={resolved(option.icon)} alt="" style={{ width: 12, height: 12,
            objectFit: 'contain', imageRendering: 'pixelated' }} />}
          {value}
        </span>
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
  return (
    <div style={styles.pluginDialog} role="dialog" aria-label={tr(dialog.option.title ?? dialog.option.label)}>
      <div style={styles.infoHeader}>
        <strong>{tr(dialog.option.title ?? dialog.option.label)}</strong>
        <button style={styles.infoClose} onClick={() => openDialog(null)} aria-label={tr('Fermer')}>✕</button>
      </div>
      {(dialog.option.options ?? []).map((option, index) => pluginOption(context, dialog.plugin, option, `dialog-${index}`))}
    </div>
  );
}
