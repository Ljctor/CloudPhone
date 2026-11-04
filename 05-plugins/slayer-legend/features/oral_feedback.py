"""Wire private oral evidence routes; never acquires a game lease or capture."""
import importlib.util
from pathlib import Path


def oral_feedback(directory):
    spec = importlib.util.spec_from_file_location("slayer_oral_feedback", Path(directory) / "oral_feedback.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {"routes": module.routes(module.OralFeedback())}
