"""Keep one private PNG example of each reliably recognised game screen.

The archive lives in the plugin data directory and survives deployments.
The web page can request one named example at a time through the read-only
examples route. Live readers still use fresh captures and their calibrated
fixtures; these examples are durable material for readers and navigation.
"""

import json
import os
import re
import struct
import zlib

SAFE = re.compile(r"^[a-z][a-z0-9_]*$")
EXCLUDE = {"panel", "better_weapon_toast"}


def screen_id(look):
    base = look.get("screen")
    overlays = [name for name in look.get("overlays", ()) if name not in EXCLUDE]
    name = overlays[-1] if overlays else base
    if name in (None, "unknown") or base == "battle" and "panel" in look.get("overlays", ()) and not overlays:
        return None
    return name if SAFE.fullmatch(name) else None


def png(shot):
    width, height, pixels = shot
    if len(pixels) != width * height * 3:
        raise ValueError("RGB capture size")

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    rows = b"".join(b"\0" + pixels[y * width * 3:(y + 1) * width * 3] for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))


def archive(directory):
    seen = set(os.listdir(directory)) if directory and os.path.isdir(directory) else set()

    def record(look, shot, now):
        name = screen_id(look)
        if not directory or not name or name + ".png" in seen:
            return None
        os.makedirs(directory, mode=0o700, exist_ok=True)
        path = os.path.join(directory, name + ".png")
        if os.path.exists(path):
            seen.add(name + ".png")
            return None
        temporary = path + ".tmp"
        with open(temporary, "wb") as file:
            file.write(png(shot))
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        seen.add(name + ".png")
        manifest = os.path.join(directory, "manifest.json")
        try:
            with open(manifest, encoding="utf-8") as file:
                entries = json.load(file)
        except (OSError, ValueError):
            entries = {}
        entries[name] = {"file": name + ".png", "captured": now,
                         "width": shot[0], "height": shot[1]}
        with open(manifest + ".tmp", "w", encoding="utf-8") as file:
            json.dump(entries, file, sort_keys=True)
        os.chmod(manifest + ".tmp", 0o600)
        os.replace(manifest + ".tmp", manifest)
        return name

    return record
