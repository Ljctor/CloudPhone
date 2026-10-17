# Part 05 — Plugins

Optional features of the Cloud Phone app (part 04), one directory per
plugin. Installed plugins show in the page's options panel (the cog in the
toolbar), under **Plugins**; without any, the page and the gateway have no
game-specific code.

| Plugin | What it adds |
|---|---|
| [`slayer-legend/`](slayer-legend/README.md) | Slayer Legend: a launch button, the emerald counter rewritten |

## Install

Part 04 must be installed. On the server, from an unpacked release:

```sh
sudo 05-plugins/scripts/install.sh                 # every plugin
sudo 05-plugins/scripts/install.sh slayer-legend   # or only some
sudo 05-plugins/scripts/install.sh --uninstall slayer-legend
```

or from a workstation: `packaging/deploy.sh SERVER 05` (every plugin). The
script copies each plugin's files (not its README) to
`/opt/cloudphone/plugins/<id>/` and restarts the gateway, which loads plugins
at start (Android keeps running). Reload the page afterwards. Upgrading part
04 keeps installed plugins.

## Writing a plugin

A directory `<id>/` (lowercase letters, digits, dashes; the same as the id
in its manifest) with:

| File | Role |
|---|---|
| `plugin.json` | `{"id": "<id>", "title": "...", "version": "..."}` |
| `page.js` | optional ES module for the page; may import the other `*.js` beside it |
| `gateway.py` | optional, `setup(context)` adds routes under `/api/v1/plugins/<id>/` |
| `README.md` | what it does, for humans (not installed) |

The API is described at the top of
`04-cloud-phone-app/src/overlay/js/example/src/plugins.ts` (page) and
`04-cloud-phone-app/src/overlay/gateway/src/videobridge_gateway/plugins.py`
(gateway).
