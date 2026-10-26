"""The game's state as the plugin last saw it: the schema (each screen of
screen_registry.json's tree and the fields it shows), which readers a
look at the screen runs (readers_for), and how a reading becomes the
state (noted). Pure: the readers are features/game.py's, the clock and
the store are passed in.

A field's fact: {value, seen (Unix time), verified, source}. source is
"scan" (read off a capture), "setup" (what a setup step checked) or
"page" (what a page sent: a stage it saw). verified turns false for every
fact when the game was stopped or relaunched (unverified): the value is
kept, the next setup reads it again. A value once seen is never null
again: a reading that gives nothing leaves the fact as it was. A field
whose reader waits for its calibration captures is "pending": it has no
fact.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESOURCES = json.loads((ROOT / "resources.json").read_text(encoding="utf-8"))
TREE = json.loads((ROOT / "screen_registry.json").read_text(encoding="utf-8"))["tree"]

SOURCES = ("scan", "setup", "page")

# Each screen's fields, by navigation.json / tree id: label (French, the
# page's), persist (kept in state.json; else in memory, for the features
# only), pending (no reader yet: its captures are on docs/TODO.md's
# calibration list), shown (how the page writes it).
SCHEMA = {
    "battle": {"label": "Jeu · Combat", "fields": {
        "stage": {"label": "Stage", "shown": "number"},
        "highest": {"label": "Stage le plus haut atteint", "shown": "lower_bound"},
        "progress": {"label": "Progression du stage", "shown": "percent"},
        "gold": {"label": "Gold", "shown": "text"},
        "preset": {"label": "Préréglage de combat", "shown": "text"},
        "emerald": {"label": "Émeraudes", "shown": "text", "pending": True},
        "diamond": {"label": "Diamants", "shown": "text", "pending": True},
        "stage_numeral": {"persist": False},
        "gold_reading": {"persist": False},
        "gold_place": {"persist": False},
    }},
    "stage_select": {"label": "Jeu · Select Region", "fields": {
        "region": {"label": "Région", "shown": "text"},
    }},
    "soul_weapon": {"label": "Jeu · Soul Weapon", "fields": {
        "soul_weapon_selected": {"label": "Arme sélectionnée", "shown": "text"},
        "soul_weapon_equipped": {"label": "Soul Weapon équipée", "shown": "text"},
        "soul_weapon_variant": {"label": "Variante de gravure", "shown": "text"},
        "souls": {"label": "Âmes", "shown": "souls"},
        "souls_reading": {"persist": False},
    }},
    "soul_weapon_engraving": {"label": "Jeu · Gravure", "fields": {
        "engraving": {"label": "Grille de gravure", "shown": "grid"},
    }},
    "mine_list": {"label": "Jeu · Mine fermée", "fields": {
        "mine_floor": {"label": "Étage de la mine", "shown": "number"},
        "mine_area": {"label": "Zone de la mine", "shown": "number"},
        "mine_feathers": {"label": "Plumes", "shown": "number", "pending": True},
    }},
}

# Resource counters have one home, independent of the screen that reads them.
for group in SCHEMA.values():
    for resource in RESOURCES:
        group["fields"].pop(resource["field"], None)
SCHEMA["soul_weapon"]["fields"]["souls"] = {"persist": True}
SCHEMA["mine_list"]["fields"].pop("mine_feathers", None)
SCHEMA["resources"] = {"label": "Ressources", "fields": {
    row["field"]: {"label": row["label"], "shown": "text", "pending": row["pending"]}
    for row in RESOURCES}}
# Keep the legacy mine reading private until its feather type is calibrated.
SCHEMA["mine_list"]["fields"]["mine_feathers"] = {"pending": True}


def screen_path(screen):
    """The access path from the game's own navigation catalogue."""
    path, visited = [], set()
    while screen and screen not in visited:
        if screen == "battle":
            break  # Battle is the base screen, not a menu to open.
        visited.add(screen)
        node = TREE.get(screen, {})
        path.insert(0, node.get("name", screen))
        screen = node.get("parent")
    return path


def forbidden_menu(screen):
    """The top-right menu and everything behind it are outside this plugin."""
    while screen:
        if screen == "top_menu":
            return True
        screen = TREE.get(screen, {}).get("parent")
    return False


FIELDS = {field: {"persist": True, "pending": False, **spec, "screen": screen}
          for screen, group in SCHEMA.items() for field, spec in group["fields"].items()}

# Which readers a look runs: on, the (base screen, overlay) pairs it reads
# (overlay "*": any or none, None: none at all, "plain": the plain battle
# screen, else that overlay over it); fields, what it may give; every, the
# seconds between two of its runs (0: on every look; a slow reader, text
# naming or the engraving grid, waits so that the looks keep their pace).
READERS = {
    "battle_stage": {"on": [("battle", "*")], "fields": ("stage", "stage_numeral"), "every": 15},
    "progress": {"on": [("battle", "plain"), ("battle", "soul_weapon")], "fields": ("progress",), "every": 0},
    "gold": {"on": [("battle", "*"), ("saver", "*")], "fields": ("gold", "gold_reading", "gold_place"),
             "every": 10},
    "saver_stage": {"on": [("saver", "*")], "fields": ("stage",), "every": 0},
    "badge": {"on": [("battle", None), ("battle", "plain")], "fields": ("preset",), "every": 0},
    "battle_settings": {"on": [("battle", "battle_settings")], "fields": ("preset",), "every": 0},
    "souls": {"on": [("battle", "soul_weapon")], "fields": ("souls", "souls_reading"), "every": 10},
    "soul_weapon": {"on": [("battle", "soul_weapon")], "fields": ("soul_weapon_selected", "soul_weapon_equipped"),
                    "every": 10},
    "region": {"on": [("battle", "stage_select")], "fields": ("region",), "every": 5},
    "engraving": {"on": [("soul_weapon_engraving", None)], "fields": ("engraving",), "every": 5},
}

# While the user plays (an input in the last PLAYING seconds with the game
# in front) a capture every PLAYING_EVERY seconds is scanned; the game's
# process is looked at every PROCESS_EVERY seconds otherwise.
PLAYING = 60
PLAYING_EVERY = 5
PROCESS_EVERY = 15
# The state is written at once when a value changes, else at most every
# SAVE_EVERY seconds (its seen times).
SAVE_EVERY = 60


def seen_screen(look, classified=None):
    """(base, overlays, plain) of a look (screens.look), the older
    classifier's name standing in when the model knows no screen: its
    battle and Power Saving Mode, and a menu as a panel over the battle."""
    base, overlays, plain = look["screen"], set(look.get("overlays") or ()), bool(look.get("plain"))
    if base == "unknown" and classified in ("battle", "saver"):
        return classified, set(), False
    if base == "unknown" and classified == "menu":
        return "battle", {"panel"}, False
    return base, overlays, plain


def readers_for(look, classified=None):
    """The readers a look at this screen runs, in READERS' order."""
    base, overlays, plain = seen_screen(look, classified)
    chosen = []
    for reader, spec in READERS.items():
        for on_base, on_overlay in spec["on"]:
            if on_base != base:
                continue
            if (on_overlay == "*" or on_overlay in overlays or (on_overlay is None and not overlays)
                    or (on_overlay == "plain" and plain)):
                chosen.append(reader)
                break
    return chosen


def due(reader, last_run, now, force=()):
    """The reader may run now: its every seconds since its last run, or
    forced."""
    every = READERS[reader]["every"]
    return reader in force or not every or last_run is None or now - last_run >= every


def fields_of(readers):
    return {field for reader in readers for field in READERS[reader]["fields"]}


# Values that move on their own while the game farms: not the user's
# changes, and written with the others at most every SAVE_EVERY seconds.
VOLATILE = ("progress", "gold", "souls")


def lasting(field):
    """A kept value that does not move on its own."""
    return FIELDS[field]["persist"] and field not in VOLATILE and FIELDS[field]["screen"] != "resources"


def fresh(saved, now):
    """The state from state.json's "game" section (checked: a field the
    schema does not hold, a source or a time of the wrong kind is left
    out). Restored facts are unverified until read again."""
    facts = {}
    for field, fact in (saved or {}).items() if isinstance(saved, dict) else ():
        spec = FIELDS.get(field)
        if not spec or not spec["persist"] or spec["pending"] or not isinstance(fact, dict):
            continue
        if fact.get("value") is None:
            continue
        if field == "engraving" and not (isinstance(fact["value"], dict) and fact["value"].get("weapon")):
            continue
        seen = fact.get("seen")
        facts[field] = {"value": fact["value"],
                        "seen": float(seen) if isinstance(seen, (int, float)) and not isinstance(seen, bool) else now,
                        "verified": False,
                        "source": fact.get("source") if fact.get("source") in SOURCES else "scan"}
    # Migrate the previous aggregate without inventing a new observation time.
    for colour, value in facts.get("souls", {}).get("value", {}).items():
        if value is not None and f"soul_{colour}" in FIELDS:
            facts.setdefault(f"soul_{colour}", {**facts["souls"], "value": value})
    return facts


def persisted(facts):
    return {field: dict(fact) for field, fact in facts.items() if FIELDS[field]["persist"]}


def _higher(before, value):
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        return None
    return value if before is None or value > before else before


def noted(facts, readings, now, source="scan"):
    """facts with readings ({field: value}; None: not read) noted at now.
    The highest stage only goes up, and a stage read raises it too.
    Returns (facts, changes): changes [(field, before, after)] for each
    known value that changed."""
    facts = dict(facts)
    changes = []
    readings = dict(readings)
    for colour, value in (readings.get("souls") or {}).items():
        readings[f"soul_{colour}"] = value
    if readings.get("stage") is not None:
        readings["highest"] = max(filter(None, (readings.get("highest"), readings["stage"])))
    for field, value in readings.items():
        if value is None or field not in FIELDS or FIELDS[field]["pending"]:
            continue
        before = facts.get(field)
        if field == "highest":
            value = _higher(before and before["value"], value)
            if value is None:
                continue
        if before is not None and before["value"] != value:
            changes.append((field, before["value"], value))
        facts[field] = {"value": value, "seen": now, "verified": True, "source": source}
    return facts, changes


def unverified(facts):
    """The game was stopped or relaunched: every fact kept, none verified."""
    return {field: {**fact, "verified": False} for field, fact in facts.items()}


def fact_now(facts, field, max_age, now):
    """The fact when it was seen within max_age seconds (None: any age),
    verified or not; else None."""
    fact = facts.get(field)
    if fact is None or (max_age is not None and now - fact["seen"] > max_age):
        return None
    return fact


def answer(facts):
    """GET /game: {screens: [{screen, label, fields: [{field, label, shown,
    pending, value, seen, verified, source}]}]}, every shown field of the
    schema, those never seen with value null."""
    screens = []
    for screen, group in SCHEMA.items():
        rows = []
        for field, spec in group["fields"].items():
            if "shown" not in spec:
                continue
            fact = facts.get(field) or {}
            rows.append({"field": field, "label": spec["label"], "shown": spec["shown"],
                         "pending": bool(spec.get("pending")), "value": fact.get("value"),
                         "seen": fact.get("seen"), "verified": fact.get("verified", False),
                         "source": fact.get("source")})
        screens.append({"screen": screen, "label": group["label"], "path": screen_path(screen), "fields": rows})
    resources = next(group["fields"] for group in screens if group["screen"] == "resources")
    known = {group["screen"]: group for group in screens if group["screen"] != "resources"}
    # Catalogue order is the menu order, with children beside their parent;
    # Battle itself is the base screen and has no menu path.
    ordered = [known.pop("battle")]
    for screen, node in TREE.items():
        if forbidden_menu(screen):
            continue
        ordered.append(known.pop(screen, {"screen": screen, "label": node["name"],
                                         "path": screen_path(screen), "fields": [], "pending": True}))
    ordered.extend(known.values())
    return {"screens": ordered, "resources": resources}


def change_line(field, before, after):
    """The log line for a value the user changed in the game."""
    return f"User changed {field} from {short(before)} to {short(after)}"


def short(value):
    text = str(value)
    return text if len(text) <= 60 else text[:57] + "..."
