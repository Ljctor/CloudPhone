"""Public game-state facade: fresh evidence, field requests and GET /game.

Construction injects a FactStore, ObservationPipeline and CaptureProducer.
The facade coordinates them without owning reader work or persistence. Its
API remains the single source of game facts for navigation and features.
"""


class GameState:
    def __init__(self, ports, rules, facts, pipeline, producer, examples=None):
        self.ports = ports
        self.clock = ports.clock
        self.rules = rules
        self.fact_store = facts
        self.pipeline = pipeline
        self.producer = producer
        self.examples = examples

    async def fresh(self, max_age=0, force=()):
        """(shot, readings) of a capture at most max_age seconds old."""
        shot = await self.ports.capture(max_age=max_age)
        return (shot, await self.pipeline.scan(shot, force) if shot else {})

    async def scan_visible(self, shot):
        """Read every calibrated reader shown by a user's final gesture frame."""
        return await self.pipeline.scan(shot, tuple(self.pipeline.registry.readers))

    async def require(self, fields, max_age=0):
        """{field: fact} for each field: the state's when seen within
        max_age seconds, else read on a fresh capture; {value: None, why}
        when this screen does not show it or it did not read."""
        now = self.clock.wall()
        answer = {
            field: self.rules.fact_now(self.fact_store.facts, field, max_age, now)
            for field in fields
        }
        if any(fact is None for fact in answer.values()):
            wanted = tuple(
                reader
                for reader, spec in self.rules.READERS.items()
                if any(field in spec["fields"] for field in fields)
            )
            shot, readings = await self.fresh(
                min(max_age, 1.0) if max_age is not None else 0, wanted
            )
            here = self.pipeline.readable_here()
            now = self.clock.wall()
            # Derived fields count only when this exact capture established them.
            # A fresh unread image cannot fall back to recent historical facts.
            confirmed, _ = self.rules.noted(
                {}, readings, self.pipeline.observed(shot)[0] if shot else now
            )
            for field in fields:
                if answer[field] is None:
                    fact = self.rules.fact_now(
                        self.fact_store.facts,
                        field,
                        max(max_age, 1.0) if max_age is not None else None,
                        now,
                    )
                    proof = confirmed.get(field)
                    if (
                        not proof
                        or not fact
                        or proof["value"] != fact["value"]
                        or proof["seen"] != fact["seen"]
                    ):
                        fact = None
                    answer[field] = fact or {
                        "value": None,
                        "why": "unread" if field in here else "not readable on this screen",
                    }
                else:
                    # Another field refresh may cross a relaunch or disprove
                    # the initially cached fact while this request awaits OCR.
                    answer[field] = self.rules.fact_now(
                        self.fact_store.facts, field, max_age, now
                    ) or {
                        "value": None,
                        "why": "unread" if field in here else "not readable on this screen",
                    }
        return answer

    async def get(self, field, max_age=0):
        return (await self.require([field], max_age))[field]

    async def handle_game(self, request):
        answer = {
            **self.rules.answer(self.fact_store.facts),
            "playing": self.producer.playing,
            "scans": self.pipeline.scans,
            "observation": {**self.pipeline.telemetry(), "producer": self.producer.telemetry()},
            "scan": self.pipeline.scan_summary(),
        }
        return self.ports.respond(self.examples(answer) if self.examples else answer)

    def feature(self):
        if hasattr(self.ports, "on_capture"):
            self.ports.on_capture(self.pipeline.saw)
        if hasattr(self.ports, "on_relaunch"):
            self.ports.on_relaunch(self.pipeline.relaunched)
        api = {
            "get": self.get,
            "require": self.require,
            "fresh": self.fresh,
            "scan": self.pipeline.scan,
            "scan_visible": self.scan_visible,
            "note": self.fact_store.note,
            "value": self.fact_store.value,
            "relaunched": self.pipeline.relaunched,
            "facts": lambda: self.fact_store.facts,
            "view": self.pipeline.view,
        }
        return {
            "routes": [("GET", "/game", self.handle_game)],
            "startup": [self.producer.start],
            "api": api,
        }


def game(ports, rules, facts, pipeline, producer, examples=None):
    return GameState(ports, rules, facts, pipeline, producer, examples).feature()
