# Part 05 — Plugins

Optional features of the Cloud Phone app (part 04), one directory per
plugin. Installed plugins show in the page's options panel (the cog in the
toolbar), under **Plugins**; without any, the page and the gateway have no
game-specific code.

| Plugin | What it adds |
|---|---|
| [`slayer-legend/`](slayer-legend/README.md) | Slayer Legend: the launch, the screen and stage, the modes and the Closed Mine's farming, gold per second, the navigation trace, the emerald and diamond counters cut or rewritten |

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

## Trust

A plugin is not sandboxed: installing one gives it everything the Cloud
Phone app has.

- Its `gateway.py` runs inside the gateway process, with the gateway's
  rights: the `cloudphone` user and its files (the alerts' topic, every
  plugin's data directory), the emulator's gRPC token (the screen, touches
  and keys) and adb on Android (any app, any setting, the signed-in
  accounts).
- Its `page.js` runs in the page, on the page's origin: it sees the video,
  reads the page token and can send any request the user can, to the
  gateway's API and to every plugin's routes.

So the only plugins are those of the release (this directory), reviewed like
the gateway's own code before they enter the repository, and installed by
root with `05-plugins/scripts/install.sh` into `/opt/cloudphone/plugins/`,
which belongs to root and which the gateway cannot write. There is no remote
install: no route, page or plugin adds, changes or downloads a plugin, and
none may be added. The gateway loads plugins only at start.

## Writing a plugin

A directory `<id>/` (lowercase letters, digits, dashes; the same as the id
in its manifest) with:

| File | Role |
|---|---|
| `plugin.json` | `{"id": "<id>", "title": "...", "version": "...", "api": 1}` |
| `page.js` | optional ES module for the page; may import the other `*.js` beside it (top level only: the gateway serves no script from a subdirectory) |
| `gateway.py` | optional, `setup(context)` adds routes under `/api/v1/plugins/<id>/` |
| other `*.py`, one level of subdirectories | modules `gateway.py` loads itself, beside it or one directory down (e.g. `features/`); installed with it, without `__pycache__`, `*.pyc`, `test_*` and Markdown |
| `test_*.py` | its tests, run in its directory (not installed) |
| `README.md` | what it does, for humans (not installed) |

`api` is the version of the plugin API the plugin is written for: the
gateway's `API_VERSION` in `plugins.py`, now `1` (a number, or
`"major.minor"`; without `api`, 1). The gateway refuses a plugin whose major
differs from its own: it runs none of its code and serves none of its
scripts, logs why, and `GET /api/v1/plugins` lists it with an `error` and no
`page`, as any plugin that failed to load once its manifest was read; the
options panel shows the error. Additions to the API (such as
`screenshot(max_age=...)` and `analyse(...)`) keep the major; a change that
breaks existing plugins raises it, and the plugins of the release move to it
in the same commit.

The API is described at the top of
`04-cloud-phone-app/src/overlay/js/example/src/plugins.ts` (page) and
`04-cloud-phone-app/src/overlay/gateway/src/videobridge_gateway/plugins.py`
(gateway).
