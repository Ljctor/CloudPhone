// Plugins: optional features installed on the server beside the app (for
// example part 05, Slayer Legend). The gateway lists them at
// /api/v1/plugins; each one with a page.js is imported here and activated
// with the API below. Their options show in the options panel, under
// "Plugins".
//
// A plugin's page.js is an ES module whose default export is
//   activate(api) => { options: Option[], dispose?(), onSetting?(key, value) }
// where an Option is one of
//   { type: 'toggle', key, label }                 stored per plugin, off by default
//   { type: 'number', key, label, placeholder? }   digits, stored as text
//   { type: 'choice', key, label, choices: [{ value, label }] }   stored as the value, first one by default
// choices and placeholder may also be functions, read at each render.
//   { type: 'action', label, button, run(), disabled?() }
//   { type: 'buttons', label, buttons: [{ label, run(), disabled?() }] }   a row of small buttons
//   { type: 'status', label, value(), href?() }    href makes the value a link
//   { type: 'section', key, label, folded? }       starts a foldable sub-section (folded: default)
//   { type: 'dialog', label, button?, title?, options: Option[] }   a button opening these
//                                                  options in a dialog over the panel
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
//   setting(key)          this plugin's stored option (true/false, or text)
//   refresh()             re-render the options panel (after a status change)
//   tr, addTranslations
import { useEffect, useRef, useState } from 'react';
import { addTranslations, tr } from './i18n';

export function usePlugins({ gatewayUrl, deviceRef, layerRef, screenWidth, settings, postHeaders }) {
  const [plugins, setPlugins] = useState([]);
  const [, setVersion] = useState(0);
  const settingsRef = useRef(settings);
  settingsRef.current = settings;
  const widthRef = useRef(screenWidth);
  widthRef.current = screenWidth;
  const active = useRef([]);

  useEffect(() => {
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
        if (!plugin.page || cancelled) continue;
        const base = `${gatewayUrl}/api/v1/plugins/${plugin.id}`;
        const layer = document.createElement('div');
        layer.style.cssText = 'position:absolute;inset:0;pointer-events:none;z-index:1;overflow:hidden';
        layerRef.current?.appendChild(layer);
        const api = {
          id: plugin.id,
          title: plugin.title,
          url: (path) => `${base}${path}`,
          get: async (path) => {
            const response = await fetch(`${base}${path}`, { cache: 'no-store' });
            return response.ok ? response.json() : null;
          },
          post: async (path, body = {}) => {
            const response = await fetch(`${base}${path}`, {
              method: 'POST', headers: postHeaders(), body: JSON.stringify(body),
            });
            return { ok: response.ok, status: response.status, body: await response.json().catch(() => ({})) };
          },
          video: () => deviceRef.current?.querySelector('video') ?? null,
          layer,
          screenWidth: () => widthRef.current,
          setting: (key) => settingsRef.current.plugins?.[plugin.id]?.[key] ?? null,
          refresh,
          tr,
          addTranslations,
        };
        try {
          const module = await import(/* @vite-ignore */ `${gatewayUrl}${plugin.page}`);
          const instance = module.default(api) ?? {};
          loaded.push({ ...plugin, instance, layer });
        } catch (error) {
          console.error(`Plugin ${plugin.id}:`, error);
          layer.remove();
          loaded.push({ ...plugin, instance: { options: [] }, error: String(error?.message ?? error) });
        }
      }
      if (cancelled) {
        loaded.forEach((item) => { item.instance.dispose?.(); item.layer?.remove(); });
        return;
      }
      active.current = loaded;
      setPlugins(loaded);
    })();
    return () => {
      cancelled = true;
      active.current.forEach((item) => { item.instance.dispose?.(); item.layer?.remove(); });
      active.current = [];
    };
  }, [gatewayUrl]);

  // Tell plugins when one of their stored options changes.
  const previous = useRef(settings.plugins ?? {});
  useEffect(() => {
    const next = settings.plugins ?? {};
    for (const plugin of active.current) {
      const before = previous.current[plugin.id] ?? {};
      const after = next[plugin.id] ?? {};
      for (const key of new Set([...Object.keys(before), ...Object.keys(after)])) {
        if (before[key] !== after[key]) plugin.instance.onSetting?.(key, after[key] ?? null);
      }
    }
    previous.current = next;
  }, [settings.plugins]);

  return plugins;
}
