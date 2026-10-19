// The plugins' options in the options panel: one foldable section per
// plugin, its options by kind (toggle, number, choice, action, buttons,
// dialog, status) and the dialog an option opens. What is stored and
// folded is worked out in pluginSettings.ts.
import React, { useEffect, useState } from 'react';
import { tr } from './i18n';
import { infoRow } from './infoRows';
import { styles } from './styles';
import {
  foldedChange, optionParts, pluginOptionChange, resolved, sectionFoldId, sectionFolded,
} from './pluginSettings';

// The dialog open over the options panel ({ plugin, option } or null);
// closing the panel closes it.
export function usePluginDialog(panel) {
  const [pluginDialog, setPluginDialog] = useState(null);
  useEffect(() => { if (panel !== 'options') setPluginDialog(null); }, [panel]);
  return [pluginDialog, setPluginDialog];
}

// A plugin's options, cut into foldable sub-sections at each
// { type: 'section', key, label, folded? } (folded: its default state).
// context, here and below: { settings, updateSettings, openDialog }.
function pluginSections(context, plugin) {
  const { settings, updateSettings } = context;
  return optionParts(plugin.instance.options).map(({ section, options }) => {
    const items = options.map(([option, index]) => pluginOption(context, plugin, option, index));
    if (!section) return <React.Fragment key="top">{items}</React.Fragment>;
    const id = sectionFoldId(plugin, section);
    const folded = sectionFolded(settings, id, section);
    return (
      <details key={id} open={!folded} style={styles.pluginSection}
        onToggle={(event) => {
          const now = !event.currentTarget.open;
          if (now !== folded) updateSettings(foldedChange(settings, 'foldedPlugins', id, now));
        }}>
        <summary style={styles.pluginSectionTitle}>{tr(section.label)}</summary>
        {items}
      </details>
    );
  });
}

function pluginOption(context, plugin, option, index) {
  const { settings, updateSettings, openDialog } = context;
  const setPluginOption = (id, key, value) => updateSettings(pluginOptionChange(settings, id, key, value));
  const key = `${plugin.id}-${index}`;
  if (!(option.visible?.() ?? true)) return null;
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
            <option key={choice.value} value={choice.value}>{tr(choice.label)}</option>
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
              onChange={() => setPluginOption(plugin.id, select.key, select.value)} />
            {tr(option.label)}
          </label>
        ) : <span style={styles.infoLabel}>{tr(option.label)}</span>}
        <button style={styles.panelButton} onClick={() => openDialog({ plugin, option })}>
          {tr(option.button ?? 'Configurer')}
        </button>
      </div>
    );
  }
  if (option.type === 'status') {
    const value = option.value?.() ?? '–';
    const href = option.href?.();
    return infoRow(tr(option.label), href
      ? <a href={href} target="_blank" rel="noreferrer" style={styles.link}>{value}</a> : value);
  }
  return null;
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
          <summary style={styles.pluginTitle}>{plugin.title}</summary>
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
