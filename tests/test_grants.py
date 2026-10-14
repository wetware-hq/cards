"""Grant history: an append-only event list in the card, scenario clock only, fails closed, never shown to agents."""
import pytest
from helpers import PATIENT, env, agent, patient
import cards

EV = '\n[[grant_event]]\ngrant_id = "{g}"\nevent = "{e}"\nat = "{at}"\n'


def card(*evs, text=PATIENT):
    return text + "".join(EV.format(g=g, e=e, at=at) for g, e, at in evs)


def test_state_follows_scenario_clock():
    c = cards.load(card(("SYNTH-GR-0002", "expired", "1937-01-20")))
    assert cards.grant_state(c, "SYNTH-GR-0002", "1937-01-19") == "current"
    assert cards.grant_state(c, "SYNTH-GR-0002", "1937-01-20") == "expired"      # at the scenario time counts
    assert cards.grant_state(c, "SYNTH-GR-0002", "1937-01-04") == "unknown"
    assert cards.grant_state(c, "SYNTH-GR-0099", "1937-01-19") == "unknown"
    assert cards.grant_state(c, "SYNTH-GR-0099", "1937-01-19", {"SYNTH-GR-0099": "1937-01-01"}) == "unknown"
    assert cards.grant_state(c, "SYNTH-GR-0001", "1937-02-01", {"SYNTH-GR-0001": "1937-02-01"}) == "revoked"
    assert cards.grant_state(c, "SYNTH-GR-0001", "1937-01-31", {"SYNTH-GR-0001": "1937-02-01"}) == "current"


def test_ended_grant_refuses_open():
    t = card(("SYNTH-GR-0001", "revoked", "1937-01-10"))
    with pytest.raises(cards.Refused) as x:
        env().session("agent", "SYNTH-AG-0001", "SYNTH-GR-0001").open(t)
    assert x.value.line_id == "RF-REVOKED" and "1937-01-10" in x.value.text
    t = card(("SYNTH-GR-0001", "expired", "1937-03-01"))
    agent(env(), text=t)                                           # not yet expired at 1937-02-01


@pytest.mark.parametrize("evs", [
    [("SYNTH-GR-0001", "granted", "1937-01-06")],                  # second granted
    [("SYNTH-GR-0001", "revoked", "1937-01-10"), ("SYNTH-GR-0001", "expired", "1937-01-11")],  # after an end
    [("SYNTH-GR-0001", "revoked", "1937-01-10"), ("SYNTH-GR-0002", "revoked", "1937-01-09")],  # out of order
    [("SYNTH-GR-0001", "paused", "1937-01-10")],
    [("SYNTH-GR-0099", "revoked", "1937-01-10")],
    [("SYNTH-GR-0001", "revoked", "soon")],
])
def test_broken_history_fails_closed(evs):
    with pytest.raises(cards.Refused):
        cards.load(card(*evs))


@pytest.mark.parametrize("cut", ['event = "granted"\nat = "1937-01-05"\n', 'at = "1937-01-05"\n'])
def test_missing_fields_fail_closed(cut):
    with pytest.raises(cards.Refused):
        cards.load(PATIENT.replace(cut, "", 1))


def test_grants_without_history_fail_closed():
    with pytest.raises(cards.Refused):
        cards.load(PATIENT.split("[[grant_event]]")[0])
    with pytest.raises(cards.Refused):
        cards.load(PATIENT.replace('at = "1937-01-05"', 'at = "1937-01-04"', 1))   # granted date disagrees


def test_history_not_a_list_fails_closed():
    with pytest.raises(cards.Refused):
        cards.load('grant_event = "granted"\n' + PATIENT.split("[[grant_event]]")[0])


def test_revoke_appends_to_history():
    p = patient(env())
    p.step("revoke", grant_id="SYNTH-GR-0001")
    assert p.card["grant_events"][-1] == {"grant_id": "SYNTH-GR-0001", "event": "revoked", "at": "1937-02-01"}


def test_current_decision_maker_view_shows_no_earlier_revocation():
    t = card(("SYNTH-GR-0001", "revoked", "1937-01-10"))
    e = env()
    dm = e.session("decision_maker", "SYNTH-AG-0002", "SYNTH-GR-0002")
    dm.open(t)
    view = " ".join(dm.patient_view())
    assert "1937-01-10" not in view and "SYNTH-GR-0001" not in view and "revoked" not in view.lower()
    assert "grant_events" not in dm.patient_view() and "1937-01-10" not in cards.header(dm.card)


def test_ended_decision_maker_not_listed_as_acting():
    c = card(("SYNTH-GR-0002", "revoked", "1937-01-10"))
    v, v0 = patient(env(), text=c).patient_view(), patient(env()).patient_view()
    assert len(v) < len(v0)
