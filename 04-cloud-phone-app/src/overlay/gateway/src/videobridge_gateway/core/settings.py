"""Emulator settings: renderer, cores and memory, optionally with a new
screen size. What may be asked given the host, the state of the last
request, and the settings the running emulator was started with.

A change restarts Android, so it shares the screen size's limit (see
core/display.py). No I/O: the host's figures, the status file's text and
the emulator's command line come in.
"""

from .texts import t

RENDERERS = ("lavapipe", "swiftshader", "swangle", "software")
# Older names of the same renderers, still accepted by the emulator.
LEGACY_RENDERERS = {"swiftshader_indirect": "swiftshader", "swangle_indirect": "swangle"}


def limits(cpus, meminfo):
    """What the page may ask for: renderers, at most every host thread
    (cpus), and the host's memory (meminfo, kB values) minus 2 GiB."""
    return {
        "renderers": list(RENDERERS),
        "maxCores": cpus,
        "maxMemoryMb": (meminfo.get("MemTotal", 0) // 1024 - 2048) // 512 * 512,
    }


def request_error(renderer, cores, memory, limits):
    """The error for renderer, cores and memory (MiB) out of limits (a
    status text, core/texts.py), else None."""
    if renderer not in RENDERERS:
        return t("renderer doit être l’un de {choices}", choices=", ".join(RENDERERS))
    if not 1 <= cores <= limits["maxCores"]:
        return t("cores doit être entre 1 et {high}", high=limits["maxCores"])
    if not 2048 <= memory <= limits["maxMemoryMb"] or memory % 512:
        return t("memoryMb doit être un multiple de 512 entre 2048 et {high}", high=limits["maxMemoryMb"])
    return None


def parse_status(pending, text):
    """The state of the last settings request: pending while its request
    file is there, else what the status file says (text None: unreadable)."""
    if pending:
        return {"state": "pending"}
    words = (text or "").split()
    if not words or words[0] not in ("applying", "done", "failed"):
        return {"state": "idle"}
    if words[0] == "failed":
        return {"state": "failed", "message": " ".join(words[1:])[:200]}
    result = {"state": words[0]}
    if len(words) in (4, 7):
        result.update(renderer=words[1], cores=words[2], memoryMb=words[3])
    if len(words) == 7:
        result.update(width=words[4], height=words[5], density=words[6])
    return result


def from_command_line(args):
    """{renderer, cores, memoryMb} of an emulator's command line (its
    arguments), or None when it is not the emulator's qemu."""
    if "qemu-system" not in args[0]:
        return None
    option = lambda name: args[args.index(name) + 1] if name in args[:-1] else None
    renderer = option("-gpu")
    return {"renderer": LEGACY_RENDERERS.get(renderer, renderer), "cores": option("-cores"),
            "memoryMb": option("-memory")}
