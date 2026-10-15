"""RF-GRANT-ENDED vs RF-REVOKED (15 Oct 12:27): RF-REVOKED only for an assistant grant that was actively revoked;
every other ended grant (expired on the scenario clock, unknown, or any decision-maker grant) is RF-GRANT-ENDED;
a missing or wrong agent id is RF-NOT-YOURS. Synthetic data only."""
import pathlib
import pytest
import cards
from messages import msg

C13 = (pathlib.Path(__file__).resolve().parent.parent / "examples" / "S13-C13.toml").read_text()
PATIENT = (pathlib.Path(__file__).resolve().parent.parent / "examples" / "patient.toml").read_text()


def _open(text, actor, actor_id, grant, now, revoked=None):
    env = cards.Env(now=now)
    env.revoked.update(revoked or {})
    s = env.session(actor, actor_id, grant)
    return env, s, (lambda: s.open(text))


def _refused(fn):
    with pytest.raises(cards.Refused) as e:
        fn()
    return e.value


def test_c13_card_loads_with_guardian_expiries():
    c = cards.load(C13)
    assert c["grants"]["SYNTH-GR-1302"]["expires_at"] == "1936-03-01"
    assert c["grants"]["SYNTH-GR-1303"]["expires_at"] == "1936-06-30"


@pytest.mark.parametrize("now,state", [("1936-02-28", "current"), ("1936-03-01", "expired"), ("1936-03-09", "expired")])
def test_expiry_uses_scenario_clock(now, state):
    assert cards.grant_state(cards.load(C13), "SYNTH-GR-1302", now) == state


def test_g13e_expired_at_resubmit_is_grant_ended():
    env, s, op = _open(C13, "decision_maker", "SYNTH-PERSON-G13E", "SYNTH-GR-1302", "1936-03-09")
    e = _refused(op)
    assert e.line_id == "RF-GRANT-ENDED" and e.text == msg("RF-GRANT-ENDED") and s.card is None


def test_g13f_still_current_before_its_expiry():
    env, s, op = _open(C13, "decision_maker", "SYNTH-PERSON-G13F", "SYNTH-GR-1303", "1936-03-09")
    op()
    assert s.card is not None


def test_g13f_expired_after_june_30():
    env, s, op = _open(C13, "decision_maker", "SYNTH-PERSON-G13F", "SYNTH-GR-1303", "1936-07-01")
    assert _refused(op).line_id == "RF-GRANT-ENDED"


def test_revoked_decision_maker_grant_is_grant_ended_not_revoked():
    env, s, op = _open(C13, "decision_maker", "SYNTH-PERSON-G13", "SYNTH-GR-1301", "1936-03-09",
                       revoked={"SYNTH-GR-1301": "1936-03-05"})
    assert _refused(op).line_id == "RF-GRANT-ENDED"


def test_revoked_decision_maker_mid_session_is_grant_ended():
    env, s, op = _open(C13, "decision_maker", "SYNTH-PERSON-G13", "SYNTH-GR-1301", "1936-03-09")
    op()
    env.revoked["SYNTH-GR-1301"] = "1936-03-09"
    e = _refused(lambda: s.step("read", field="allergies"))
    assert e.line_id == "RF-GRANT-ENDED"


def test_actively_revoked_assistant_grant_is_rf_revoked():
    env, s, op = _open(PATIENT, "agent", "SYNTH-AG-0001", "SYNTH-GR-0001", "1937-03-09",
                       revoked={"SYNTH-GR-0001": "1937-03-05"})
    e = _refused(op)
    assert e.line_id == "RF-REVOKED" and e.text == msg("RF-REVOKED", date="1937-03-05")


@pytest.mark.parametrize("actor,aid,grant", [("agent", "SYNTH-AG-0999", "SYNTH-GR-0001"),
                                             ("agent", "SYNTH-AG-0001", "SYNTH-GR-0999"),
                                             ("decision_maker", "SYNTH-AG-0001", "SYNTH-GR-0001")])
def test_missing_or_wrong_agent_id_is_not_yours(actor, aid, grant):
    env, s, op = _open(PATIENT, actor, aid, grant, "1937-03-09")
    assert _refused(op).line_id == "RF-NOT-YOURS"


@pytest.mark.needs_signed
def test_six_probes_text_from_signed_files():
    """Ruling 15 Oct 12:30: one probe each; expected text read from the signed source, never WORDING.md."""
    from test_signed_sources import signed_rows
    rows = signed_rows()
    sub = lambda k, **f: rows[k][0].replace("[date]", f.get("date", "[date]"))
    probes = [
        (PATIENT, "agent", "SYNTH-AG-0001", "SYNTH-GR-0999", "1937-03-09", None, "RF-NOT-YOURS", {}),      # missing grant
        (PATIENT, "agent", "SYNTH-AG-0999", "SYNTH-GR-0001", "1937-03-09", None, "RF-NOT-YOURS", {}),      # wrong agent
        (PATIENT, "agent", "SYNTH-AG-0001", "SYNTH-GR-0001", "1937-03-09", {"SYNTH-GR-0001": "1937-03-05"},
         "RF-REVOKED", {"date": "1937-03-05"}),                                                             # stopped assistant
        (C13, "decision_maker", "SYNTH-PERSON-G13E", "SYNTH-GR-1302", "1936-03-09", None, "RF-GRANT-ENDED", {}),  # expired
        (C13, "decision_maker", "SYNTH-PERSON-G13", "SYNTH-GR-1301", "1936-03-09", {"SYNTH-GR-1301": "1936-03-05"},
         "RF-GRANT-ENDED", {}),                                                                             # revoked DM
        (C13, "decision_maker", "SYNTH-PERSON-G13F", "SYNTH-GR-1301", "1936-03-09", None, "RF-NOT-YOURS", {}),  # other's grant
    ]
    for text, actor, aid, grant, now, rev, line, f in probes:
        env, s, op = _open(text, actor, aid, grant, now, rev)
        e = _refused(op)
        assert (e.line_id, e.text) == (line, sub(line, **f)), (aid, grant)


def test_grant_not_yet_live_is_not_yours_not_ended():
    env, s, op = _open(C13, "decision_maker", "SYNTH-PERSON-G13", "SYNTH-GR-1301", "1935-12-01")
    assert _refused(op).line_id == "RF-NOT-YOURS"


def test_grant_expiring_mid_session_is_grant_ended_on_next_action():
    env, s, op = _open(C13, "decision_maker", "SYNTH-PERSON-G13F", "SYNTH-GR-1303", "1936-06-29")
    op()
    env.now = "1936-06-30"
    assert _refused(lambda: s.step("read", field="allergies")).line_id == "RF-GRANT-ENDED"
    assert env.log[-1]["event"] == "CL-REFUSED"


def test_assistant_revoked_mid_session_is_rf_revoked():
    env, s, op = _open(PATIENT, "agent", "SYNTH-AG-0001", "SYNTH-GR-0001", "1937-03-09")
    op()
    env.revoked["SYNTH-GR-0001"] = "1937-03-09"
    e = _refused(lambda: s.step("read", field="allergies"))
    assert e.line_id == "RF-REVOKED" and e.text == msg("RF-REVOKED", date="1937-03-09")


@pytest.mark.parametrize("exp", ["1936-01-02", "1936-01-01"])
def test_grant_expiring_on_or_before_its_start_fails_load(exp):
    with pytest.raises(Exception):
        cards.load(C13.replace('expires_at = "1936-03-01"', f'expires_at = "{exp}"'))
