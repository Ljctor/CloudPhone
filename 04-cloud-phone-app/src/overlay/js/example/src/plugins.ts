// Plugins: optional features installed on the server beside the app (for
// example part 05, Slayer Legend). The gateway lists them at
// /api/v1/plugins; each one with a page.js is imported here and activated
// with the API below. Their options show in the options panel, under
// "Plugins".
//
// A plugin's page.js is an ES module whose default export is
//   activate(api) => { options: Option[], icon?, dispose?(), onSetting?(key, value) }
// icon: an image URL (a data: URL drawn by the plugin, say) shown before its title
// where an Option is one of
//   { type: 'toggle', key, label }                 stored per plugin, off by default
//   { type: 'number', key, label, placeholder? }   digits, stored as text
//   { type: 'choice', key, label, choices: [{ value, label }] }   stored as the value, first one by default
// choices and placeholder may also be functions, read at each render.
//   { type: 'action', label, button, run(), disabled?() }
//   { type: 'buttons', label, buttons: [{ label, run(), disabled?() }] }   a row of small buttons
//   { type: 'status', label, value(), href?(), button?(), muted?(), look? }   href makes the value a link;
//                                                  muted() true greys the value out;
//                                                  button() => { label, run() }, a list of them,
//                                                  or null: small buttons after the value, while
//                                                  it gives some; value() gives a text or a list
//                                                  of parts, each a text or { icon, text } (icon:
//                                                  an image URL before the text, at its own size);
//                                                  look: 'game' writes the value in white with a
//                                                  1 px black outline, as a game writes numbers
//   { type: 'grid', label, rows() }               a grid of fixed-size cells, rows() =>
//                                                  [[cell, ...], ...], a cell: a CSS colour (filled),
//                                                  'empty' (outlined) or null (not part of the grid)
//   { type: 'log', match?(record) }               the server's log records match() keeps
//                                                  ({time, level, source, text[, template,
//                                                  params]}; all without it), with the level filter
//   { type: 'section', key, label, folded?, icon?, depth? } starts a foldable section;
//                                                  depth 1 by default, deeper sections nest under it
//   { type: 'dialog', label, button?, title?, options: Option[], select? }   a button opening
//                                                  these options in a dialog over the panel;
//                                                  select: { key, value, default } puts a radio
//                                                  button before the label (stored as key = value),
//                                                  select.disabled?() greys it out (not configured);
//                                                  options: [] shows no button
// Any option may have visible?(): shown only when it returns true.
// Labels are French; the plugin gives English texts with api.addTranslations.
// api:
//   id, title
//   url(path)             /api/v1/plugins/<id><path>
//   get(path)             GET, parsed JSON or null
//   post(path, body)      POST with the page token: { ok, status, body }
//   video()               the <video> element showing Android, or null
//   layer                 a <div> over the screen for drawing, pointer-events none
//   screenWidth()         width of the shown screen in CSS pixels
//   setting(key)          this plugin's stored option (true/false, or text),
//                         kept by the gateway in the plugin's data directory
//                         for every browser; plugins start once they are read
//   adopt(key, value)     stores value as the option, as the gateway says it
//                         is now (a timed mode that ended): onSetting is not
//                         called for it, so the plugin does not send it back
//   refresh()             re-render the options panel (after a status change)
//   warn(text, params?)   a warning record in this page's log (Client tab,
//                         nothing pops up over the screen), in
//                         English like every log record: text is a French
//                         text with its English entry, an English text, or
//                         {template, params}; e.g. a setting the gateway refused
//   onTap(listener)       calls listener({ x, y, kind[, end] }) after each touch
//                         the user makes on the Android screen, once the finger
//                         lifts (it has already reached Android; this only
//                         observes). x, y: where it started, fractions of the
//                         screen (0..1 from the top left); kind 'tap', 'long'
//                         (held 500 ms or more) or 'swipe' (moved), with end:
//                         { x, y } where a swipe ended. Returns a function that
//                         stops it; stopped anyway when the plugin is unloaded.
//   tr(text, params?)     text in the page's language: a French text, or
//                         {template, params} as a gateway sends one (a param
//                         of that shape translated too, others are data)
//   addTranslations(english)   { French: English } entries, kept first come
import { useEffect, useRef, useState } from 'react';
import { addTranslations, english, tr } from './i18n';
import { pageLog } from './logs';
import { pluginOptionChange } from './pluginSettings';

// Every plugin's onTap listeners; App.tsx calls emitTap at each touch end.
const tapListeners = new Set();

export function emitTap(tap) {
  for (const listener of tapListeners) {
    try {
      listener(tap);
    } catch (error) {
      console.error('Plugin tap listener:', error);
    }
  }
}

function stopTaps(taps) {
  for (const listener of taps ?? []) tapListeners.delete(listener);
  taps?.clear();
}

function unload(item) {
  item.instance.dispose?.();
  item.layer?.remove();
  stopTaps(item.taps);
}

export function usePlugins({
  gatewayUrl, deviceRef, layerRef, screenWidth, settings, updateSettings, postFetch, postHeaders,
  settingsLoaded = true,
}) {
  const [plugins, setPlugins] = useState([]);
  const [, setVersion] = useState(0);
  const settingsRef = useRef(settings);
  settingsRef.current = settings;
  const updateRef = useRef(updateSettings);
  updateRef.current = updateSettings;
  // The options a plugin adopted: their next change is not told back to it.
  const adopted = useRef({});
  const widthRef = useRef(screenWidth);
  widthRef.current = screenWidth;
  const active = useRef([]);

  useEffect(() => {
    // The plugins start with the gateway's settings, not the defaults.
    if (!settingsLoaded) return undefined;
    let cancelled = false;
    const refresh = () => setVersion((value) => value + 1);
    (async () => {
      let list = [];
      try {
        const response = await fetch(`${gatewayUrl}/api/v1/plugins`, { cache: 'no-store' });
        if (response.ok) list = (await response.json()).plugins ?? [];
      } catch {
        list = [];
      }
      const loaded = [];
      for (const plugin of list) {
        if (cancelled) continue;
        // Refused by the gateway (another plugin API, gateway code failing):
        // shown with its error, nothing to import.
        if (plugin.error) {
          loaded.push({ ...plugin, instance: { options: [] } });
          continue;
        }
        if (!plugin.page) continue;
        const base = `${gatewayUrl}/api/v1/plugins/${plugin.id}`;
        const layer = document.createElement('div');
        layer.style.cssText = 'position:absolute;inset:0;pointer-events:none;z-index:1;overflow:hidden';
        layerRef.current?.appendChild(layer);
        const taps = new Set();
        const api = {
          id: plugin.id,
          title: plugin.title,
          url: (path) => `${base}${path}`,
          get: async (path) => {
            const response = await fetch(`${base}${path}`, { cache: 'no-store' });
            return response.ok ? response.json() : null;
          },
          post: async (path, body = {}) => {
            const response = await postFetch(`${base}${path}`, {
              method: 'POST', headers: postHeaders(), body: JSON.stringify(body),
            });
            return { ok: response.ok, status: response.status, body: await response.json().catch(() => ({})) };
          },
          video: () => deviceRef.current?.querySelector('video') ?? null,
          layer,
          screenWidth: () => widthRef.current,
          setting: (key) => settingsRef.current.plugins?.[plugin.id]?.[key] ?? null,
          adopt: (key, value) => {
            if ((settingsRef.current.plugins?.[plugin.id]?.[key] ?? null) === value) return;
            adopted.current[`${plugin.id}\u0000${key}`] = value;
            updateRef.current?.(pluginOptionChange(settingsRef.current, plugin.id, key, value));
          },
          refresh,
          warn: (text, params) => pageLog('warning', `${plugin.title ?? plugin.id}: ${english(text, params)}`),
          onTap: (listener) => {
            taps.add(listener);
            tapListeners.add(listener);
            return () => {
              taps.delete(listener);
              tapListeners.delete(listener);
            };
          },
          tr,
          addTranslations,
        };
        try {
          const module = await import(/* @vite-ignore */ `${gatewayUrl}${plugin.page}`);
          const instance = module.default(api) ?? {};
          loaded.push({ ...plugin, instance, layer, taps });
        } catch (error) {
          console.error(`Plugin ${plugin.id}:`, error);
          layer.remove();
          stopTaps(taps);
          loaded.push({ ...plugin, instance: { options: [] }, error: String(error?.message ?? error) });
        }
      }
      if (cancelled) {
        loaded.forEach(unload);
        return;
      }
      active.current = loaded;
      setPlugins(loaded);
    })();
    return () => {
      cancelled = true;
      active.current.forEach(unload);
      active.current = [];
    };
  }, [gatewayUrl, settingsLoaded]);

  // Tell plugins when one of their stored options changes.
  const previous = useRef(settings.plugins ?? {});
  useEffect(() => {
    const next = settings.plugins ?? {};
    for (const plugin of active.current) {
      const before = previous.current[plugin.id] ?? {};
      const after = next[plugin.id] ?? {};
      for (const key of new Set([...Object.keys(before), ...Object.keys(after)])) {
        if (before[key] === after[key]) continue;
        const id = `${plugin.id}\u0000${key}`;
        if (id in adopted.current && adopted.current[id] === (after[key] ?? null)) {
          delete adopted.current[id];
          continue;
        }
        delete adopted.current[id];
        plugin.instance.onSetting?.(key, after[key] ?? null);
      }
    }
    previous.current = next;
  }, [settings.plugins]);

  return plugins;
}
