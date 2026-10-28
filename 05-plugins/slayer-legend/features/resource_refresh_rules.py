"""Autonomous resource visits: eligibility, required evidence and bounds.
No game input or runtime guesses. Geometry stays in navigation.json.
"""
HOLDER = "resource_refresh"
MODES = ("mpw18", "mpw4")
EVERY = 300
POLL = 2
WAIT = 4
FRAME_POLL = .25
DEADLINE = 60
MOST_SCROLLS = 4
BOOTSTRAP_GAP = 10
RETURN_RESERVE = 15
REQUIRED_SCREENS = ("battle", "equipment_weapon", "equipment_accessories", "weapon_detail", "soul_weapon")
MOVES = {"battle": ("menu_equipment",),
         "equipment_weapon": ("inspect_weapon", "scroll", "accessories", "soul_weapon"),
         "equipment_accessories": ("weapon", "scroll"), "weapon_detail": ("close",), "soul_weapon": ("close",)}


def eligible(mode, enabled, recovery=None):
    return bool(enabled and mode.get("configured") is True and mode.get("mode") in MODES
                and not mode.get("setup") and not mode.get("hold")
                and mode.get("state") not in ("moving", "waiting")
                and not (recovery or {}).get("required"))


def missing(screens, navigation, equipment):
    absent = [name for name in REQUIRED_SCREENS
              if screens.REGISTRY.get(name, {}).get("status") != "registered"
              or not screens.REGISTRY[name].get("fixtures")]
    for screen, names in MOVES.items():
        moves = navigation.connections(screen)
        for name in names:
            if not any(move.get("id") == name and not move.get("forbidden") for move in moves):
                absent.append(f"{screen}/{name}")
    if not getattr(equipment, "INSPECT_LEARNED", False) or not callable(getattr(equipment, "inspect_weapon_safe", None)):
        absent.append("inspect_weapon_safe")
    if not getattr(equipment, "SCROLL_LEARNED", False) or not callable(getattr(equipment, "scroll_safe", None)):
        absent.append("equipment_scroll_safe")
    for screen in ("equipment_weapon", "equipment_accessories"):
        if not any(area.get("measured") and area.get("move") == f"{screen}/scroll"
                   for area in screens.TREE.get(screen, {}).get("scroll", ())):
            absent.append(f"{screen}/scroll_geometry")
    return absent
