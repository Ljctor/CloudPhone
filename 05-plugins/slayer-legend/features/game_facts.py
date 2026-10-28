"""Game facts: persistence, capture-time publication and user-change reporting.

Unread observations retain their historical value but revoke verification.
A separate watermark remembers that newer unread evidence, so delayed OCR
cannot make an older frame authoritative again.
"""

PLUGIN = ("launch", "mine", "watchdog", "mode", "stage_change", "resource_refresh")


class FactStore:
    def __init__(self, ports, rules):
        self.ports = ports
        self.rules = rules
        self.clock = ports.clock
        self.facts = rules.fresh(ports.store.saved.get("game"), self.clock.wall())
        self.saved_at = self.clock.monotonic()
        self.watermarks = {}
        ports.store.register("game", lambda: rules.persisted(self.facts))
        # Earlier releases persisted highest separately; migrate as unverified history.
        kept = [
            ports.store.saved.get("highest"),
            (ports.store.saved.get("mode") or {}).get("highest"),
        ]
        kept = [n for n in kept if isinstance(n, int) and not isinstance(n, bool) and n > 0]
        if kept and "highest" not in self.facts:
            self.facts, _ = rules.noted(
                self.facts, {"highest": max(kept)}, self.clock.wall(), "setup"
            )
            self.facts = rules.unverified(self.facts)

    def save(self, changed):
        if changed or self.clock.monotonic() - self.saved_at >= self.rules.SAVE_EVERY:
            self.saved_at = self.clock.monotonic()
            self.ports.store.save()

    def note(self, readings, source="scan", seen=None):
        """Notes readings ({field: value}); logs the user's changes. Written
        at once when a lasting value changed or a field is first seen,
        else at most every SAVE_EVERY seconds."""
        before = self.facts
        self.facts, changes = self.rules.noted(
            before, readings, self.clock.wall() if seen is None else seen, source
        )
        held = self.ports.lease.state() if hasattr(self.ports, "lease") else None
        ours = bool(held and held.get("holder") in PLUGIN)
        lasting = [change for change in changes if self.rules.lasting(change[0])]
        if source == "scan" and not ours:
            for field, old, new in lasting:
                self.ports.log("normal", self.rules.change_line(field, old, new))
        self.save(
            bool(lasting) or any(field not in before and field in self.facts for field in readings)
        )
        return changes

    def value(self, field):
        fact = self.facts.get(field)
        return fact["value"] if fact else None

    def publish(self, readings, seen):
        """Publish one reader result; return the number of rejected older fields."""
        accepted = {
            field: value
            for field, value in readings.items()
            if seen >= self.watermarks.get(field, float("-inf"))
        }
        for field in accepted:
            self.watermarks[field] = seen
        self.note(accepted, seen=seen)
        return len(readings) - len(accepted)

    def invalidate(self, why):
        self.watermarks.clear()
        self.facts = self.rules.unverified(self.facts)
        self.ports.log("normal", f"Game {why}: every game value unverified until read again")
        self.ports.store.save()
