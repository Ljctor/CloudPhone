"""The gateway's texts the page shows to the user, as status texts.

A refusal the page shows (POST /api/v1/emulator-settings's, in its dialog)
is never a finished sentence: {"error_t": {template, params}}, a fixed
French template (the page's base language) and its parameters (data, shown
as they are). TEMPLATES gives each template's English, served as it is by
GET /api/v1/templates for the page's translations. The log and the answers
the page never shows stay English (english()).

Pure.
"""

TEMPLATES = {
    "Attendez {seconds} s avant le prochain changement": "Wait {seconds} s before the next change",
    "Les changements de réglages d’Android sont désactivés": "Emulator settings changes are disabled",
    "Un changement est déjà en cours": "A change is already in progress",
    "cores doit être entre 1 et {high}": "cores must be between 1 and {high}",
    "memoryMb doit être un multiple de 512 entre 2048 et {high}":
        "memoryMb must be a multiple of 512 between 2048 and {high}",
    "renderer doit être l’un de {choices}": "renderer must be one of {choices}",
    "renderer, cores et memoryMb sont requis": "renderer, cores and memoryMb are required",
    "width et height doivent être pairs": "width and height must be even",
    "width, height et density vont ensemble": "width, height and density go together",
    "{key} doit être entre {low} et {high}": "{key} must be between {low} and {high}",
}


def t(template, **params):
    """A status text: the fixed French template and its parameters."""
    return {"template": template, "params": params}


def english(text):
    """The English of a status text, filled (a plain string is already
    English)."""
    if not isinstance(text, dict):
        return "" if text is None else str(text)
    out = TEMPLATES.get(text["template"], text["template"])
    for key, value in (text.get("params") or {}).items():
        out = out.replace(f"{{{key}}}", str(value))
    return out
