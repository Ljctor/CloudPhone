"""The page's options, kept on the server so that every browser and device
shows the same ones: the page's own (language, cursor, folding, docked
bar, folded sections, log filter) in one file, and each plugin's options
in its own file in that plugin's data directory.

Settings are a JSON object; "plugins" holds {plugin id: {key: value}}.
A change is merged: a top-level key replaces its value, a plugin's key
replaces that key's value, null removes it. Secrets never come here: the
alerts' topic stays in its own file (core/alerts.py).

No I/O: saved texts and changes come in, the merged settings and the
texts to save come out.
"""

import json
import re

# A plugin's id (as plugins.py accepts it).
PLUGIN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
# The saved text of one file, at most (the page's settings are small).
MOST = 64 * 1024


def parse_saved(text):
    """The object a saved file holds; {} when missing (None), broken or
    not an object."""
    try:
        saved = json.loads(text) if text is not None else None
    except ValueError:
        return {}
    return saved if isinstance(saved, dict) else {}


def saved_text(settings):
    return json.dumps(settings, sort_keys=True, ensure_ascii=False)


def check_change(change):
    """The change as given, or ValueError: an object whose "plugins", if
    there, is {plugin id: object}, and whose text stays under MOST."""
    if not isinstance(change, dict) or not change:
        raise ValueError("Expected a non-empty object of settings")
    plugins = change.get("plugins", {})
    if not isinstance(plugins, dict):
        raise ValueError("plugins: expected {plugin id: {key: value}}")
    for plugin_id, options in plugins.items():
        if not PLUGIN_ID.match(plugin_id) or not isinstance(options, dict):
            raise ValueError(f"plugins.{plugin_id}: expected an id and an object")
    if len(saved_text(change)) > MOST:
        raise ValueError("Settings too large")
    return change


def merged(current, change):
    """current with change applied: top-level keys replaced, null removes."""
    result = dict(current)
    for key, value in change.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = value
    if len(saved_text(result)) > MOST:
        raise ValueError("Settings too large")
    return result


def split(change):
    """(the page's own part, {plugin id: options}) of a checked change."""
    own = {key: value for key, value in change.items() if key != "plugins"}
    return own, dict(change.get("plugins", {}))


def answer(own, plugins):
    """GET's settings: the page's own with "plugins" ({id: options})."""
    return {**{key: value for key, value in own.items() if key != "plugins"}, "plugins": plugins}
