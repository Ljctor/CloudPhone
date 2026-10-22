"""The launch's steps (features/launch_rules.py) and the launch itself
(features/launch.py) on fake ports, the sign-in screen above all: "Sign in
with Google" once per launch, Google's chooser only when it lists exactly
one account, never Apple's button; and Google's chooser read from
uiautomator (ports.chooser_window, ports.accounts).
Run: python3 -m unittest test_launch"""

import asyncio
import contextlib
import importlib.util
import os
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(f"slayer_legend_{name.replace('/', '_')}",
                                                  os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rules = load("features/launch_rules")
launch = load("features/launch")
ports_module = load("features/ports")
screens = load("screens")
nav = load("nav")


def steps(screens_seen, every=rules.LOOK_EVERY):
    """The moves for screens seen one look apart."""
    memory, moves = rules.fresh(), []
    for i, screen in enumerate(screens_seen):
        move, memory = rules.step(screen, memory, 100.0 + every * i)
        moves.append(move)
    return moves


class SignInSteps(unittest.TestCase):
    def test_google_once_then_its_chooser_then_the_save(self):
        self.assertEqual(steps(["sign_in", "sign_in", "chooser_one", "other", "save"]),
                         ["sign_in", "wait", "choose_account", "wait", "confirm"])

    def test_the_sign_in_screen_back_is_for_the_user(self):
        moves = steps(["sign_in"] + ["sign_in"] * 10)
        self.assertEqual(moves.count("sign_in"), 1, "one try per launch")
        self.assertEqual(moves[-1], "blocked_sign_in")
        self.assertEqual(moves[1:7], ["wait"] * 6, "inside SIGN_IN_WAIT: the chooser may be coming")

    def test_a_chooser_with_none_or_several_accounts_stops(self):
        self.assertEqual(steps(["sign_in", "chooser_other"]), ["sign_in", "blocked_chooser"])

    def test_the_one_account_is_chosen_once(self):
        self.assertEqual(steps(["sign_in", "chooser_one", "chooser_one"]), ["sign_in", "choose_account", "wait"])

    def test_a_chooser_the_launch_did_not_open_is_not_tapped(self):
        self.assertEqual(steps(["chooser_one"]), ["wait"])

    def test_the_title_and_save_as_before(self):
        self.assertEqual(steps(["title", "save"]), ["start", "confirm"])


class Guard(unittest.TestCase):
    def test_google_is_allowed_apple_never(self):
        self.assertIsNone(nav.guard("sign_in", "google", *screens.SIGN_IN_GOOGLE_TAP))
        self.assertIn("forbidden", nav.guard("sign_in", "apple", 0.5, 0.812))
        self.assertIn("not where", nav.guard("sign_in", "google", 0.5, 0.812))

    def test_the_account_needs_its_reading(self):
        self.assertIn("needs a check", nav.guard("account_chooser", "account", 0.5, 0.5))
        self.assertIsNone(nav.guard("account_chooser", "account", 0.5, 0.5, verified=True))


GMS_FOCUS = ("  mCurrentFocus=Window{3c u0 com.google.android.gms/"
             "com.google.android.gms.common.account.AccountPickerActivity}\n")


def node(text, bounds, package="com.google.android.gms"):
    return f'<node index="0" text="{text}" package="{package}" class="android.widget.TextView" bounds="{bounds}" />'


def hierarchy(*nodes):
    return "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation=\"0\">" + "".join(nodes) + \
        "</hierarchy>"


class Chooser(unittest.TestCase):
    def test_googles_window_in_front(self):
        self.assertTrue(ports_module.chooser_window(GMS_FOCUS))
        self.assertFalse(ports_module.chooser_window(
            "  mCurrentFocus=Window{1 u0 com.gear2.growslayer/com.google.firebase.MessagingUnityPlayerActivity}"))

    def test_one_account_its_name_and_address_once(self):
        found = ports_module.accounts(hierarchy(
            node("Choose an account", "[40,300][440,340]"), node("Some Player", "[120,400][400,430]"),
            node("player@example.com", "[120,430][400,460]"), node("PLAYER@example.com", "[120,600][400,630]"),
            node("Add another account", "[120,520][400,560]")))
        self.assertEqual(found, [(260, 445)])

    def test_two_accounts_and_other_apps_nodes(self):
        self.assertEqual(len(ports_module.accounts(hierarchy(
            node("a@example.com", "[0,0][10,10]"), node("b@example.com", "[0,20][10,30]")))), 2)
        self.assertEqual(ports_module.accounts(hierarchy(node("a@example.com", "[0,0][10,10]", "com.other"))), [])
        self.assertEqual(ports_module.accounts("ERROR: could not get idle state."), [])


class Ports:
    """Fake ports for launch.py: one screen per look ("chooser:n": Google's
    chooser listing n accounts, the game's last screen behind it)."""

    class Busy(RuntimeError):
        pass

    def __init__(self, looks):
        self.looks, self.seen, self.taps, self.alerts, self.now = list(looks), None, [], [], 0.0
        test = self

        class clock:
            monotonic = staticmethod(lambda: test.now)

            @staticmethod
            async def sleep(seconds):
                test.now += seconds

        self.clock = clock

    @contextlib.asynccontextmanager
    async def leased(self, holder, reason, seconds, user=False):
        yield

    async def start_game(self):
        return True

    async def capture(self):
        self.seen = self.looks.pop(0) if self.looks else "other"
        return (480, 1040, self.seen)

    async def crashed(self):
        return False

    async def analyse(self, fn, shot):
        return fn(shot)

    async def focused(self):
        return not self.seen.startswith("chooser")

    async def account_chooser(self):
        if not self.seen.startswith("chooser"):
            return None
        count = int(self.seen.split(":")[1])
        return {"count": count, "point": (240, 445) if count == 1 else None}

    def guarded(self, screen, move, point, verified=False):
        refusal = nav.guard(screen, move, point[0], point[1], verified=verified)
        if refusal:
            raise RuntimeError(refusal)
        self.taps.append((screen, move))

    async def tap(self, shot, screen, move, point, verified=False):
        self.guarded(screen, move, point, verified)

    async def hold(self, shot, screen, move, point, milliseconds):
        self.guarded(screen, move, point)

    async def choose_account(self, shot, point):
        self.guarded("account_chooser", "account", (point[0] / 480, point[1] / 1040), True)

    async def close_crash(self, shot):
        return False

    async def notify(self, text):
        self.alerts.append(text)

    def spawn(self, coroutine):
        return asyncio.get_running_loop().create_task(coroutine)

    respond = staticmethod(lambda body, status=200: body)
    log = staticmethod(ports_module.python_log("slayer-legend"))
    exception = staticmethod(ports_module.exception_log(log))


def launched(looks):
    """(taps, alerts, the launch's last state) for screens seen look by look."""
    fake = Ports(looks)
    fake_screens = types.SimpleNamespace(**{name: getattr(screens, name) for name in dir(screens)
                                            if name.isupper()})
    fake_screens.classify = lambda shot: shot[2]
    built = launch.launch(fake, fake_screens, rules)

    async def run():
        await built["api"]["start"]("watchdog", False)

    asyncio.run(run())
    return fake.taps, fake.alerts, built["api"]["state"]()


for name, value in ports_module.text_ports().items():
    setattr(Ports, name, staticmethod(value))


class SignInLaunch(unittest.TestCase):
    def test_google_then_the_one_account_then_confirm_then_battle(self):
        taps, alerts, state = launched(["sign_in", "chooser:1", "other", "save", "battle"])
        self.assertEqual(taps, [("sign_in", "google"), ("account_chooser", "account"), ("save_notice", "confirm")])
        self.assertEqual((alerts, state["state"]), ([], "done"))

    def test_the_sign_in_screen_back_is_one_alert(self):
        taps, alerts, state = launched(["sign_in"] * 12)
        self.assertEqual(taps, [("sign_in", "google")])
        self.assertEqual(state["state"], "blocked")
        self.assertEqual(len(alerts), 1)
        self.assertIn("Google sign-in impossible: to do by hand", alerts[0])

    def test_several_accounts_is_one_alert_and_no_tap(self):
        taps, alerts, state = launched(["sign_in", "chooser:2"])
        self.assertEqual(taps, [("sign_in", "google")])
        self.assertEqual((len(alerts), state["state"]), (1, "blocked"))
        self.assertIn("2 accounts", alerts[0])

    def test_no_account_listed_is_one_alert_and_no_tap(self):
        taps, alerts, _ = launched(["sign_in", "chooser:0"])
        self.assertEqual((taps, len(alerts)), ([("sign_in", "google")], 1))


if __name__ == "__main__":
    unittest.main()
