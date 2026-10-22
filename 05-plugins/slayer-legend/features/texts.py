"""The plugin's texts, in two kinds.

- What the page shows as a status (a mode's or the mine's message, an
  error in an answer, the watchdog's line) is never a finished sentence:
  {template, params} (t()), a fixed French template (the page's base
  language) and its parameters, which the page translates with
  templates.json beside the plugin ({French template: English}, served by
  GET /templates). A parameter is data, shown as it is (a stage, a
  weapon's name), or itself a {template, params} (a fixed name such as a
  repair's, a reason): never a French string to translate.
- The log and the phone alerts are English, whatever the page's language:
  english() fills a template's English from the same table, for a status
  that is also logged or alerted; a text only logged or alerted is
  written in English where it is said.

Pure, but for reading templates.json once.
"""

import json
import os

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates.json")
_table = {}


def table():
    """{French template: English} (templates.json)."""
    if not _table:
        with open(PATH, encoding="utf-8") as f:
            _table.update(json.load(f))
    return _table


def t(template, **params):
    """A status text: the fixed French template and its parameters."""
    return {"template": template, "params": params}


def is_t(value):
    return isinstance(value, dict) and isinstance(value.get("template"), str)


def fill(text, params, inner):
    """text with each {key} replaced by its parameter (inner(value) for a
    nested template), as the page's tr does: other braces stay as they are."""
    for key, value in (params or {}).items():
        text = text.replace(f"{{{key}}}", str(inner(value) if is_t(value) else value))
    return text


def english(value):
    """The English of a status text (a template not in the table, its
    French: the contract test keeps the table complete); a plain string
    is already English."""
    if not is_t(value):
        return "" if value is None else str(value)
    return fill(table().get(value["template"], value["template"]), value.get("params"), english)


def french(value):
    """The French of a status text, filled."""
    if not is_t(value):
        return "" if value is None else str(value)
    return fill(value["template"], value.get("params"), french)
