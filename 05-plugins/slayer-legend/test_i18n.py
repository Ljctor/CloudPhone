"""English means English: a source lint of the page's texts.

    cd 05-plugins/slayer-legend && python3 -m unittest test_i18n

The page (part 04's js/example/src) and this plugin's page side (*.js
here) are written in French; tr() gives the English entry of a text when
English is chosen and falls back to French without one. So:

- every French literal (an accented letter, or a French word) outside the
  English tables is a key of one: part 04's EN for part 04, part 04's EN
  or one of this plugin's ENGLISH tables for the plugin;
- no table entry is orphaned: each key is a literal of its sources, or for
  the plugin a template of templates.json (the gateway's texts, sent as
  {template, params});
- templates.json, when there, gives each template an English text with
  the same {placeholders} and no French;
- an entry's English has the same {placeholders} as its French.

Log records are English already (written with english(), or by the
server): their literals are keys like any other.

Not installed on the server (install.sh skips test_*.py).
"""

import glob
import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "..", "..", "04-cloud-phone-app", "src", "overlay", "js", "example", "src")
TEMPLATES = os.path.join(HERE, "templates.json")

ACCENTS = re.compile(r"[àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒÆ«»]")
# French words that are no English words.
FRENCH_WORDS = set("""
le la les des du de un une et est pas pour sur avec dans en au aux ou ne sans par mais cette ce ces qui
que sa ses mes tu il elle nous vous leur deux oui non rien aucun aucune jeu libre choisir choisis fermer
touchez touche serveur appareil réglages étage fermée
""".split())
WORD = re.compile(r"[\wÀ-ÿœŒ’'-]+")
# Shown as they are in either language: a language's own name, language
# and locale ids.
DATA = {"Français", "en", "fr", "en-GB", "fr-FR"}
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def french(text):
    if text in DATA:
        return False
    return bool(ACCENTS.search(text)) or any(w.lower() in FRENCH_WORDS for w in WORD.findall(text))


def literals(source, jsx=False):
    """The string literals of a JS/TS source, comments left out: '...',
    "...", and template literals (their ${...} parts read as code, the
    literal kept with ${} in their place); with jsx, also the text between
    JSX tags."""
    out = []
    code = []
    i, n = 0, len(source)
    while i < n:
        c = source[i]
        if source.startswith("//", i):
            j = source.find("\n", i)
            i = n if j < 0 else j
            continue
        if source.startswith("/*", i):
            j = source.find("*/", i)
            i = n if j < 0 else j + 2
            continue
        if c in "'\"":
            j, text = i + 1, ""
            while j < n and source[j] != c:
                if source[j] == "\\":
                    text += source[j + 1:j + 2]
                    j += 2
                    continue
                text += source[j]
                j += 1
            out.append(text)
            code.append(" ")
            i = j + 1
            continue
        if c == "`":
            j, text, depth, inner = i + 1, "", 0, ""
            while j < n:
                if depth == 0 and source[j] == "`":
                    break
                if depth == 0 and source.startswith("${", j):
                    depth, inner, text = 1, "", text + "${}"
                    j += 2
                    continue
                if depth:
                    if source[j] == "{":
                        depth += 1
                    elif source[j] == "}":
                        depth -= 1
                        if depth == 0:
                            out.extend(literals(inner))
                            j += 1
                            continue
                    inner += source[j]
                else:
                    text += source[j]
                j += 1
            out.append(text)
            code.append(" ")
            i = j + 1
            continue
        code.append(c)
        i += 1
    if jsx:
        for match in re.finditer(r">([^<>{}]*[A-Za-zÀ-ÿ][^<>{}]*)<", "".join(code)):
            out.append(match.group(1).strip())
    return out


def split_table(source, start):
    """(source without the table, {French: English}) for the object literal
    opened by `start` (e.g. "const EN = {"), or (source, {}) without one."""
    if start not in source:
        return source, {}
    a = source.index(start)
    b = source.index("\n};", a)
    found = literals(source[a + len(start):b])
    table = dict(zip(found[0::2], found[1::2]))
    return source[:a] + source[b:], table


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def sources(paths, start):
    """{path: literals outside the table}, and the tables merged."""
    texts, tables = {}, {}
    for path in paths:
        rest, table = split_table(read(path), start)
        tables.update(table)
        texts[path] = literals(rest, jsx=path.endswith(".tsx"))
    return texts, tables


class PageTexts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plugin, cls.plugin_en = sources(sorted(glob.glob(os.path.join(HERE, "*.js"))), "const ENGLISH = {")
        page_files = sorted(glob.glob(os.path.join(PAGE, "*.ts")) + glob.glob(os.path.join(PAGE, "*.tsx")))
        cls.page, cls.page_en = sources(page_files, "const EN = {")
        cls.templates = None
        if os.path.exists(TEMPLATES):
            with open(TEMPLATES, encoding="utf-8") as f:
                cls.templates = json.load(f)

    def test_the_sources_are_found(self):
        self.assertIn("Mode et farming", self.plugin_en)
        self.assertTrue(self.page, "part 04's page sources at " + PAGE)
        self.assertIn("Fermer", self.page_en)

    def test_every_french_literal_of_the_plugin_has_its_english(self):
        known = set(self.plugin_en) | set(self.page_en)
        missing = sorted({f"{os.path.basename(path)}: {text}" for path, found in self.plugin.items()
                          for text in found if french(text) and text not in known})
        self.assertEqual(missing, [], "French texts with no English entry")

    def test_every_french_literal_of_the_page_has_its_english(self):
        missing = sorted({f"{os.path.basename(path)}: {text}" for path, found in self.page.items()
                          for text in found if french(text) and text not in self.page_en})
        self.assertEqual(missing, [], "French texts with no English entry")

    def test_no_english_entry_of_the_page_is_orphaned(self):
        used = {text for found in self.page.values() for text in found}
        self.assertEqual(sorted(set(self.page_en) - used), [], "entries no source uses")

    def test_no_english_entry_of_the_plugin_is_orphaned(self):
        used = {text for found in self.plugin.values() for text in found} | set(self.templates or {})
        self.assertEqual(sorted(set(self.plugin_en) - used), [], "entries neither a literal nor a template")

    def test_english_entries_keep_their_placeholders_and_have_no_french(self):
        for table in (self.page_en, self.plugin_en, self.templates or {}):
            for source, english in table.items():
                with self.subTest(source=source):
                    self.assertIsInstance(english, str)
                    self.assertTrue(english.strip(), "an empty English text")
                    self.assertEqual(sorted(PLACEHOLDER.findall(source)), sorted(PLACEHOLDER.findall(english)))
                    self.assertFalse(french(english), f"French in the English text {english!r}")

    def test_templates_json_is_flat_french_to_english(self):
        if self.templates is None:
            self.skipTest("no templates.json yet")
        self.assertIsInstance(self.templates, dict)
        for source, english in self.templates.items():
            with self.subTest(source=source):
                self.assertIsInstance(source, str)
                self.assertIsInstance(english, str)


if __name__ == "__main__":
    unittest.main()
