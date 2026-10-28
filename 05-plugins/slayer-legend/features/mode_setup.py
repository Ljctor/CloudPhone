"""Receipts and evidence for an accepted farming loadout.

The mode orchestrator supplies its current mode, mine override and whether a
transaction is active. This component owns the setup gates and attempt/result
identity; it performs no navigation, scheduling, logging or persistence.
Inject ``mode_setup`` into ``mode(..., setup_factory)`` at composition time.
"""

import copy
from typing import NamedTuple


class SetupAttempt(NamedTuple):
    generation: int
    mode: str
    stage: int
    revision: object
    target: dict
    input_mark: object
    launch_epoch: int


class SetupEvidence:
    """Track one attempt and expose only current, revision-bound evidence."""

    RESULT_SECONDS = 120

    def __init__(self, ports, loadouts, farming):
        self.ports = ports
        self.loadouts = loadouts
        self.farming = farming
        self._result = None
        self._generation = 0
        self._launch_epoch = 0
        if callable(getattr(ports, "on_relaunch", None)):
            ports.on_relaunch(self.invalidate_launch)

    def _input_mark(self):
        latest = self.ports.last_input() if callable(getattr(self.ports, "last_input", None)) else None
        return (latest.get("wall"), latest.get("monotonic")) if isinstance(latest, dict) else None

    def engraving_off(self, mode):
        """A configured engraving is requested while its execution switch is off."""
        switch = self.farming.get("engraving_switch")
        if mode not in ("mpw18", "mpw4") or switch is None or switch() != "off":
            return False
        weapon = self.loadouts["loadout"](mode).get("soul_weapon") or {}
        variant = self.loadouts.get("variant")
        return bool(weapon.get("variant") and variant and variant(weapon.get("id"), weapon["variant"]))

    def blocker(self, mode, mine_enabled=False):
        """Current execution gate; no first-run history is inferred from an off switch."""
        if mode not in ("mpw18", "mpw4") or mine_enabled:
            return None
        chosen = self.loadouts["loadout"](mode).get("soul_weapon")
        if not chosen:
            return None
        switch = self.farming.get("soul_weapon_switch")
        if switch and switch() == "off":
            return self.ports.t("Soul Weapon désactivée : configuration demandée non appliquée")
        capability = self.loadouts.get("applicability")
        support = capability(chosen) if capability else None
        if support and not support["supported"]:
            return support.get("reason_t")
        if (not support or support.get("engraving_required", True)) and self.engraving_off(mode):
            return self.ports.t("Gravure automatique désactivée · premier passage soumis à supervision")
        return None

    def request(self, mode, *, configured, mine_enabled=False, busy=False):
        """An actionable accepted-target receipt, never equipment evidence."""
        revision = self.loadouts.get("revision")
        if (not self.ports.enabled() or not configured or mode not in ("mpw18", "mpw4")
                or mine_enabled or not self.loadouts["stage"](mode)
                or not revision or self.blocker(mode, mine_enabled) or busy):
            return None
        return {"mode": mode, "if_revision": revision(mode)}

    def invalidate_launch(self, *_args):
        self._launch_epoch += 1

    def clear_result(self):
        """A new accepted execution cannot inherit the previous attempt's result."""
        self._generation += 1
        self._result = None

    @property
    def has_result(self):
        return self._result is not None

    def begin_attempt(self, mode, stage):
        """Snapshot the full target and acquisition identity before any await."""
        self.clear_result()
        revision = self.loadouts.get("revision")
        return SetupAttempt(self._generation, mode, stage, revision(mode) if revision else None,
                            copy.deepcopy(self.loadouts["loadout"](mode)), self._input_mark(), self._launch_epoch)

    def complete_attempt(self, attempt, *, mode, completed, state, message):
        """Record the actual outcome only while the original target remains current."""
        revision = self.loadouts.get("revision")
        if (not revision or attempt.generation != self._generation or mode != attempt.mode
                or attempt.revision != revision(attempt.mode) or attempt.target.get("stage") != attempt.stage
                or attempt.input_mark != self._input_mark() or attempt.launch_epoch != self._launch_epoch):
            return
        self._result = {"mode": attempt.mode, "revision": attempt.revision,
                        "target": copy.deepcopy(attempt.target), "at": self.ports.clock.wall(),
                        "result": "done" if completed else state, "message_t": copy.deepcopy(message),
                        "input_mark": attempt.input_mark, "launch_epoch": attempt.launch_epoch}

    def current_result(self, mode, mine_enabled=False):
        """A detached public result; input, launch, revision or age can invalidate it."""
        result = self._result
        revision = self.loadouts.get("revision")
        if not result or not revision or result["mode"] != mode or mine_enabled:
            return None
        age = self.ports.clock.wall() - result["at"]
        if (not 0 <= age <= self.RESULT_SECONDS or result["revision"] != revision(mode)
                or result["input_mark"] != self._input_mark() or result["launch_epoch"] != self._launch_epoch):
            return None
        return copy.deepcopy({key: value for key, value in result.items() if key not in ("input_mark", "launch_epoch")})


def mode_setup(ports, loadouts, farming):
    """Composition factory for the mode's setup receipt/evidence component."""
    return SetupEvidence(ports, loadouts, farming)
