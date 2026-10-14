"""Card sleeve over a fake harness (same session/observe/step/call interface as the stack harness)."""
import pytest
from helpers import cards, PATIENT, PROVIDER, env
import sleeve


class FakeHandle:
    def __init__(self, h, actor, role, patient):
        self.h, self.actor, self.role, self.patient = h, actor, role, patient

    def observe(self, ep, *a, note=None):
        self.h.calls.append((self.actor, "observe", a))
        return "seen"

    def step(self, ep, action, note=None):
        self.h.calls.append((self.actor, "step", action))
        return "done"

    def call(self, ep, method, *a):
        self.h.calls.append((self.actor, method, a))
        return "refused"


class FakeHarness:
    def __init__(self):
        self.calls, self.trace = [], ["t"]

    def session(self, actor, role, patient, discipline=None, scope=()):
        self.calls.append((actor, "session", role))
        return FakeHandle(self, actor, role, patient)


CARDS = {"SYNTH-P0101": {"text": PATIENT},
         "SYNTH-agent-01": {"text": PATIENT, "grant": "SYNTH-GR-0001", "agent_id": "SYNTH-AG-0001"},
         "SYNTH-dr-01": {"text": PROVIDER},
         "SYNTH-cagent-01": {"text": PROVIDER, "agent_id": "SYNTH-AG-0009"}}


def make():
    h = FakeHarness()
    return h, sleeve.SleevedHarness(h, sleeve.Sleeve(h, env(), CARDS))


def test_pass_through_unchanged():
    h, sh = make()
    a = sh.session("SYNTH-agent-01", "patient_agent", "SYNTH-P0101")
    assert a.step("EP", {"type": "answer"}) == "done" and a.observe("EP", 1) == "seen" and a.call("EP", "reset") == "refused"
    d = sh.session("SYNTH-dr-01", "clinician", "SYNTH-P0101", discipline="medicine")
    assert d.step("EP", {"type": "approve"}) == "done"
    assert sh.trace == ["t"]
    assert [c[1] for c in h.calls] == ["session", "step", "observe", "reset", "session", "step"]


def test_actor_needs_a_card_and_one_session():
    h, sh = make()
    with pytest.raises(cards.Refused):
        sh.session("SYNTH-nobody", "patient", "SYNTH-P0101")
    sh.session("SYNTH-P0101", "patient", "SYNTH-P0101")
    with pytest.raises(cards.Refused) as e:
        sh.session("SYNTH-P0101", "patient", "SYNTH-P0101")
    assert e.value.line_id == "RF-ONE-PROFILE"
    assert [c[1] for c in h.calls] == ["session"]


@pytest.mark.parametrize("actor,role,disc", [("SYNTH-P0101", "clinician", "medicine"),
                                              ("SYNTH-dr-01", "patient", None),
                                              ("SYNTH-dr-01", "clinician", "nursing")])
def test_role_must_match_card(actor, role, disc):
    h, sh = make()
    with pytest.raises(cards.Refused) as e:
        sh.session(actor, role, "SYNTH-P0101", discipline=disc)
    assert e.value.line_id == "RF-REG-UNVERIFIED" and h.calls == []


def test_unverified_provider_never_reaches_harness():
    h = FakeHarness()
    s = sleeve.Sleeve(h, cards.Env({}, {}), CARDS)
    with pytest.raises(cards.Refused):
        s.session("SYNTH-dr-01", "clinician", "SYNTH-P0101", discipline="medicine")
    assert h.calls == []


@pytest.mark.parametrize("t,line", [("approve", "RF-SIGN-APPROVE"), ("review", "RF-SIGN-CLOSE"),
                                    ("set_alert_route", "RF-SIGN-ROUTE"), ("sign", "RF-SIGN-LETTER")])
def test_provider_agent_sign_refused_before_harness(t, line):
    h, sh = make()
    a = sh.session("SYNTH-cagent-01", "clinician_agent", "SYNTH-P0101")
    with pytest.raises(cards.Refused) as e:
        a.step("EP", {"type": t})
    assert e.value.line_id == line and [c[1] for c in h.calls] == ["session"]
    assert a.step("EP", {"type": "answer"}) == "done"


def test_patient_agent_not_blocked_by_sign_rule():
    h, sh = make()
    a = sh.session("SYNTH-agent-01", "patient_agent", "SYNTH-P0101")
    assert a.step("EP", {"type": "approve"}) == "done"


def test_ended_session_refused():
    h = FakeHarness()
    s = sleeve.Sleeve(h, env(), CARDS)
    a = s.session("SYNTH-agent-01", "patient_agent", "SYNTH-P0101")
    s.end("SYNTH-agent-01")
    s.end("SYNTH-agent-01")
    for fn in (lambda: a.step("EP", {"type": "answer"}), lambda: a.observe("EP"), lambda: a.call("EP", "x")):
        with pytest.raises(cards.Refused) as e:
            fn()
        assert e.value.line_id == "RF-SESSION-ENDED"
    assert [c[1] for c in h.calls] == ["session"]


def test_toml_card_round_trip():
    t = sleeve.toml_card({"card_id": "SYNTH-CARD-0300", "kind": "patient", "display_name": "B. Oakes",
                          "person_name": "B. Oakes", "role": "patient", "scope": ["read"], "issued": "1934-01-01",
                          "expires": "1934-12-31", "episode_id": "SYNTH-EP-0300"},
                         grants=[{"grant_id": "SYNTH-GR-0300", "agent_id": "SYNTH-AG-0300", "agent_name": "Helper",
                                  "categories": ["general"], "granted": "1934-01-02"}])
    c = cards.load(t)
    assert c["header"]["scope"] == ["read"] and "SYNTH-GR-0300" in c["grants"]


@pytest.mark.needs_signed
def test_sleeve_refusals_carry_their_own_signed_text():
    import signing
    from test_signed_sources import signed_rows
    rows = signed_rows()
    msg = lambda k: rows[k][0]                         # expected text from the signed source, never WORDING.md
    h, sh = make()
    cases = [lambda: sh.session("SYNTH-nobody", "patient", "SYNTH-P0101"),
             lambda: sh.session("SYNTH-P0101", "clinician", "SYNTH-P0101", discipline="medicine"),
             lambda: sh.session("SYNTH-dr-01", "clinician", "SYNTH-P0101", discipline="nursing")]
    for fn in cases:
        with pytest.raises(cards.Refused) as e:
            fn()
        assert e.value.text == msg(e.value.line_id)
    a = sh.session("SYNTH-cagent-01", "clinician_agent", "SYNTH-P0101")
    with pytest.raises(cards.Refused) as e:
        a.step("EP", {"type": "approve"})
    assert e.value.text == msg(e.value.line_id)
    s = sleeve.Sleeve(FakeHarness(), env(), CARDS)
    b = s.session("SYNTH-agent-01", "patient_agent", "SYNTH-P0101"); s.end("SYNTH-agent-01")
    with pytest.raises(cards.Refused) as e:
        b.observe("EP")
    assert e.value.text == msg(e.value.line_id) and e.value.line_id == "RF-SESSION-ENDED"
