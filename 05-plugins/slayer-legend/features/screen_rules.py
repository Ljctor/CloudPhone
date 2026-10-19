"""What the screen feature answers, from what was read off the screen and
the stage table (stages.json: {fields, stages}). Pure: the table and
stage.py are passed in, nothing is read or kept here."""


def stage_info(table, number, checked):
    if not number or number > len(table["stages"]):
        return {"number": number, "name": None, "checked": checked}
    info = dict(zip(table["fields"], table["stages"][number - 1]))
    return {"number": number, "checked": checked, **info}


def name_numeral(table, stage, number):
    """The Roman numeral ending the stage's name in the table, or None."""
    if not number or number > len(table["stages"]):
        return None
    last = table["stages"][number - 1][0].rsplit(" ", 1)[-1]
    if not last or any(c not in "IVX" for c in last):
        return None
    return stage._roman(last)


def remembered(table, text):
    """The stage number the page last saw (?known=N), or None when it is
    not a plausible one."""
    try:
        number = int(text)
    except ValueError:
        return None
    return number if 1 <= number <= len(table["stages"]) + 400 else None


def answer(table, stage, screen, read, known):
    """GET /screen's answer for a screen and what was read on it (see
    screen_facts), known: the stage last farmed. Returns (answer, farmed):
    farmed is the number read in Power Saving Mode when it can be trusted
    (its numeral agrees with the table), else None."""
    if screen == "saver":
        number, numeral = read
        if number and (numeral is None or name_numeral(table, stage, number) in (None, numeral)):
            return {"screen": screen, "stage": stage_info(table, number, True)}, number
    elif screen in ("battle", "menu") and known:
        numeral = read
        checked = numeral is not None and numeral == name_numeral(table, stage, known)
        return {"screen": screen, "stage": stage_info(table, known, checked)}, None
    return {"screen": screen, "stage": stage_info(table, known, False) if known else None}, None


def higher(highest, number):
    """The new highest stage seen farmed, or None when number is not above it."""
    if not number or (highest and number <= highest):
        return None
    return number


def stage_list(table, mpw, highest):
    """Stages with that many monsters per wave, at most `highest`,
    highest first: [{number, name, colour}]."""
    found = []
    for number in range(min(highest or len(table["stages"]), len(table["stages"])), 0, -1):
        row = table["stages"][number - 1]
        if row[1] == mpw:
            found.append({"number": number, "name": row[0], "colour": row[4]})
    return found
