"""The texts the server emits, read in the sources (no gateway, no
Android): the gateway's (04-cloud-phone-app/.../videobridge_gateway) and
this plugin's.

- Logs and phone alerts are English: no literal in a logging, log(),
  notify, alert, say, record or fill call has an accented letter, « », or a
  French word.
- A status text the page shows is {template, params} with a fixed French
  template: every French-looking literal is a template, listed in
  templates.json (the plugin's) or core/texts.py's TEMPLATES (the
  gateway's), whose English is English and has the same {params}.
- Nothing asks the user to do something by hand: no « à la main », « by
  hand » or « manually » in a log, an alert, a template or its English.

Run: python3 -m unittest test_texts"""

import ast
import glob
import importlib.util
import json
import os
import re
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GATEWAY = os.path.join(HERE, "..", "..", "04-cloud-phone-app", "src", "overlay", "gateway", "src",
                       "videobridge_gateway")
# Accented letters (not × or ÷), French quotes and apostrophe.
ACCENT = re.compile(r"[À-ÖØ-öø-ÿŒœ«»’]")
FRENCH_WORDS = re.compile(r"\b(le|la|les|du|des|au|aux|une|pas|est|sont|dans|pour|avec|sur|ne|plus|déjà|"
                          r"par|de|et|ou|il|ce|cette|en attente|en cours|à|tu|toi|ton|ta|joues)\b", re.I)
BY_HAND = re.compile(r"à la main|by hand|manually", re.I)
# The calls whose text is a log record or a phone alert.
EMITTERS = {"log", "notify", "alert", "say", "record", "fill", "remember", "exception",
            "debug", "info", "warning", "error", "critical"}
# Templates that are another agent's to fix (soul_weapon_rules.py): skipped
# here only while they are still in the sources.
OTHERS = {"arme {weapon} inconnue ou de nom partagé (à équiper à la main)"}


def french(text):
    return bool(ACCENT.search(text) or FRENCH_WORDS.search(text))


def sources(root, pattern):
    return sorted(p for p in glob.glob(os.path.join(root, pattern), recursive=True)
                  if not os.path.basename(p).startswith("test_") and "/proto/" not in p)


def plugin_sources():
    return sources(HERE, "features/*.py") + sources(HERE, "*.py")


def gateway_sources():
    return sources(GATEWAY, "**/*.py")


def literals(path):
    """(emitted, others): the string literals of path's code (docstrings
    left out), those inside an emitting call apart; f-strings give their
    constant parts."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    docs = {id(node.body[0].value) for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)}
    emitted, others = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if name in EMITTERS:
                for arg in [*node.args, *(k.value for k in node.keywords)]:
                    for inner in ast.walk(arg):
                        if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                            emitted.add(inner.value)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            others.add(node.value)
    return emitted, others - emitted


def placeholders(text):
    return set(re.findall(r"\{(\w+)\}", text))


def plugin_templates():
    with open(os.path.join(HERE, "templates.json"), encoding="utf-8") as f:
        return json.load(f)


def gateway_templates():
    spec = importlib.util.spec_from_file_location("gateway_texts", os.path.join(GATEWAY, "core", "texts.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TEMPLATES


class Logs(unittest.TestCase):
    def test_logs_and_alerts_are_english(self):
        for path in plugin_sources() + gateway_sources():
            emitted, _ = literals(path)
            said = sorted(text for text in emitted if french(text) or BY_HAND.search(text))
            self.assertEqual(said, [], os.path.relpath(path, HERE))

    def test_the_lint_sees_a_french_log(self):
        tree = 'ports.log("normal", "Mine : en attente")\nlogging.info(f"Bail tenu par {x}")\n'
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "probe.py")
            with open(path, "w", encoding="utf-8") as f:
                f.write(tree)
            emitted, _ = literals(path)
        self.assertEqual(sorted(text for text in emitted if french(text)), ["Bail tenu par ", "Mine : en attente"])


class Templates(unittest.TestCase):
    def check(self, paths, table, where):
        for path in paths:
            _, others = literals(path)
            missing = sorted(text for text in others
                             if french(text) and text not in table and text not in OTHERS and text.strip())
            self.assertEqual(missing, [], f"{os.path.relpath(path, HERE)}: not in {where}")
        for template, english in table.items():
            if template in OTHERS:
                continue
            self.assertFalse(BY_HAND.search(template) or BY_HAND.search(english), template)
            self.assertFalse(french(english), f"{template!r}: {english!r} is not English")
            self.assertEqual(placeholders(template), placeholders(english), template)

    def test_every_french_text_of_the_plugin_is_a_template_with_its_english(self):
        self.check(plugin_sources(), plugin_templates(), "templates.json")

    def test_every_french_text_of_the_gateway_is_a_template_with_its_english(self):
        self.check(gateway_sources(), gateway_templates(), "core/texts.py TEMPLATES")

    def test_the_others_are_still_there(self):
        """An entry of OTHERS fixed in the sources leaves OTHERS too."""
        found = set()
        for path in plugin_sources():
            found |= literals(path)[1]
        self.assertEqual(OTHERS - found, set())


if __name__ == "__main__":
    unittest.main()
