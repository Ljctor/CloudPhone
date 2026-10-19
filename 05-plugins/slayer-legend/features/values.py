"""Values read back from state.json, checked: what is not of the expected
kind is None. Pure."""


def number_or_none(value, top):
    return value if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= top else None


def time_or_none(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
